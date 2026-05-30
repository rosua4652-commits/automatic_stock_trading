import asyncio
import time
from typing import Callable, Optional

from app.config import settings
from app.engine.portfolio import PortfolioManager
from app.market.binance import binance
from app.market.coin_registry import coin_meta
from app.market.scanner import scan_market
from app.models import AppConfig, BotState, BotStatus, CoinCandidate, CoinMeta, CoinView


class TradingEngine:
    def __init__(self, portfolio: PortfolioManager) -> None:
        self.portfolio = portfolio
        self.config = AppConfig()
        self.bot = BotState()
        self._task: Optional[asyncio.Task] = None
        self._listeners: list[Callable[[], None]] = []

    def is_running(self) -> bool:
        return self.bot.status == BotStatus.RUNNING

    def subscribe(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def _notify(self) -> None:
        for cb in self._listeners:
            try:
                cb()
            except Exception:
                pass

    async def start(self) -> None:
        if self.bot.status == BotStatus.RUNNING:
            return
        self.bot.status = BotStatus.RUNNING
        self.bot.message = "시장 분석을 시작합니다..."
        self._task = asyncio.create_task(self._loop())
        self._notify()

    async def stop(self) -> None:
        if self.bot.status == BotStatus.STOPPED:
            return
        self.bot.status = BotStatus.STOPPING
        self.bot.message = "자동투자 중지 중..."
        self._notify()

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=8.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._task = None

        self.bot.status = BotStatus.STOPPED
        self.bot.message = "자동투자가 중지되었습니다"
        self._notify()

    def update_config(self, cfg: AppConfig) -> None:
        self.config = cfg
        self._notify()

    def set_view_symbol(self, symbol: str) -> str:
        sym = symbol.upper()
        self.bot.view_symbol = sym
        self._notify()
        return sym

    async def _loop(self) -> None:
        try:
            while self.is_running():
                try:
                    await self._tick()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    if self.is_running():
                        self.bot.message = f"오류 복구 중: {e}"
                if not self.is_running():
                    break
                for _ in range(settings.scan_interval_sec):
                    if not self.is_running():
                        return
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            if self.bot.status != BotStatus.STOPPED:
                self.bot.status = BotStatus.STOPPED
                self.bot.message = "자동투자가 중지되었습니다"
            self._task = None

    async def _tick(self) -> None:
        if not self.is_running():
            return

        self.portfolio.usdt_krw = await binance.usdt_krw_rate()
        if not self.is_running():
            return

        candidates = await scan_market(limit=15, is_running=self.is_running)
        if not self.is_running():
            return

        self.bot.candidates = candidates
        self.bot.last_scan = time.time()
        self.bot.message = f"{len(candidates)}개 우량 코인 분석 완료"
        self._notify()

        tickers = await binance.tickers_24h()
        prices: dict[str, float] = {}

        for symbol in list(self.portfolio.positions.keys()):
            if not self.is_running():
                return
            t = tickers.get(symbol)
            if not t:
                continue
            price = float(t["lastPrice"])
            prices[symbol] = price
            await self._manage_position(symbol, price)

        if not self.is_running():
            return

        held = set(self.portfolio.positions.keys())
        slots = settings.max_positions - len(held)
        if slots <= 0:
            return

        snap = self.portfolio.snapshot(prices, self.config)
        per_slot = snap.cash_krw / max(slots, 1) * 0.85

        for cand in candidates:
            if not self.is_running() or slots <= 0:
                break
            if cand.symbol in held:
                continue
            if cand.score < 40:
                continue
            t = tickers.get(cand.symbol)
            if not t:
                continue
            price = float(t["lastPrice"])
            vol_pct = abs(cand.change_24h) / 100
            sl = min(0.10, max(settings.default_stop_loss_pct, vol_pct * 0.8))
            tp = min(0.25, max(settings.default_take_profit_pct, vol_pct * 1.5))

            pos = self.portfolio.buy(
                cand.symbol,
                cand.base,
                price,
                per_slot,
                sl,
                tp,
                score=cand.score,
            )
            if pos:
                prices[cand.symbol] = price
                held.add(cand.symbol)
                slots -= 1
                self.bot.recent_trades = self.portfolio.trades[-20:]

        self._notify()

    async def _manage_position(self, symbol: str, price: float) -> None:
        pos = self.portfolio.positions.get(symbol)
        if not pos:
            return

        pos.current_price = price
        if price > pos.trailing_high:
            pos.trailing_high = price

        pnl_pct = (price - pos.avg_price) / pos.avg_price

        if pnl_pct >= settings.trailing_activate_pct:
            trail_stop = pos.trailing_high * (1 - settings.trailing_distance_pct)
            pos.stop_loss = max(pos.stop_loss, trail_stop)

        if price <= pos.stop_loss:
            if self.portfolio.sell(symbol, price, "손절"):
                self.bot.recent_trades = self.portfolio.trades[-20:]
            return

        if price >= pos.take_profit:
            if self.portfolio.sell(symbol, price, "익절"):
                self.bot.recent_trades = self.portfolio.trades[-20:]
            return

        if pnl_pct <= -0.12:
            if self.portfolio.sell(symbol, price, "급락 방어"):
                self.bot.recent_trades = self.portfolio.trades[-20:]

    async def get_candles(self, symbol: str, interval: str = "1h") -> list[dict]:
        raw = await binance.klines(symbol, interval, 200)
        return [
            {
                "time": int(r[0] // 1000),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),
            }
            for r in raw
        ]

    async def prices_map(self) -> dict[str, float]:
        tickers = await binance.tickers_24h()
        out: dict[str, float] = {}
        for sym in self.portfolio.positions:
            t = tickers.get(sym)
            if t:
                out[sym] = float(t["lastPrice"])
        sym = self.bot.view_symbol
        if sym in tickers:
            out[sym] = float(tickers[sym]["lastPrice"])
        return out

    def build_coin_view(
        self,
        symbol: str,
        prices: dict[str, float],
        tickers: dict | None = None,
    ) -> CoinView:
        meta_dict = coin_meta(symbol)
        meta = CoinMeta(symbol=symbol, **meta_dict)
        price = prices.get(symbol, 0.0)
        change = 0.0

        pos = self.portfolio.positions.get(symbol)
        cand = next((c for c in self.bot.candidates if c.symbol == symbol), None)

        if tickers and symbol in tickers:
            t = tickers[symbol]
            if not price:
                price = float(t.get("lastPrice", 0))
            change = float(t.get("priceChangePercent", 0))
        if pos:
            price = pos.current_price or price
        elif cand and not change:
            change = cand.change_24h

        return CoinView(
            meta=meta,
            price_usdt=price,
            change_24h=change,
            in_portfolio=pos is not None,
            position=pos,
            candidate=cand,
        )

    def tab_symbols(self) -> list[str]:
        seen: set[str] = set()
        tabs: list[str] = [self.bot.view_symbol]
        seen.add(self.bot.view_symbol)
        for sym in self.portfolio.positions:
            if sym not in seen:
                tabs.append(sym)
                seen.add(sym)
        for c in self.bot.candidates:
            if c.symbol not in seen:
                tabs.append(c.symbol)
                seen.add(c.symbol)
        return tabs

import asyncio
import time
from typing import Callable, Optional

from app.config import settings
from app.engine.portfolio import PortfolioManager
from app.market.binance import binance
from app.market.scanner import scan_market
from app.models import AppConfig, BotState, BotStatus, CoinCandidate


class TradingEngine:
    def __init__(self, portfolio: PortfolioManager) -> None:
        self.portfolio = portfolio
        self.config = AppConfig()
        self.bot = BotState()
        self._task: Optional[asyncio.Task] = None
        self._listeners: list[Callable[[], None]] = []

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
        self.bot.message = "시장 분석 중..."
        self._task = asyncio.create_task(self._loop())
        self._notify()

    async def stop(self) -> None:
        self.bot.status = BotStatus.STOPPED
        self.bot.message = "중지됨"
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._notify()

    def update_config(self, cfg: AppConfig) -> None:
        self.config = cfg
        self._notify()

    async def _loop(self) -> None:
        while self.bot.status == BotStatus.RUNNING:
            try:
                await self._tick()
            except Exception as e:
                self.bot.message = f"오류 복구 중: {e}"
            await asyncio.sleep(settings.scan_interval_sec)

    async def _tick(self) -> None:
        self.portfolio.usdt_krw = await binance.usdt_krw_rate()
        candidates = await scan_market(limit=15)
        self.bot.candidates = candidates
        self.bot.last_scan = time.time()
        self.bot.message = f"{len(candidates)}개 우량 코인 분석 완료"

        prices: dict[str, float] = {}
        tickers = await binance.tickers_24h()

        # manage exits first
        for symbol in list(self.portfolio.positions.keys()):
            t = tickers.get(symbol)
            if not t:
                continue
            price = float(t["lastPrice"])
            prices[symbol] = price
            await self._manage_position(symbol, price)

        # entries
        held = set(self.portfolio.positions.keys())
        slots = settings.max_positions - len(held)
        if slots <= 0:
            self._notify()
            return

        snap = self.portfolio.snapshot(prices, self.config)
        per_slot = snap.cash_krw / max(slots, 1) * 0.85

        for cand in candidates:
            if slots <= 0:
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
                if not self.bot.selected_symbol or self.bot.selected_symbol not in held:
                    self.bot.selected_symbol = cand.symbol

        self._notify()

    async def _manage_position(self, symbol: str, price: float) -> None:
        pos = self.portfolio.positions.get(symbol)
        if not pos:
            return

        pos.current_price = price
        if price > pos.trailing_high:
            pos.trailing_high = price

        pnl_pct = (price - pos.avg_price) / pos.avg_price

        # trailing stop after profit threshold
        if pnl_pct >= settings.trailing_activate_pct:
            trail_stop = pos.trailing_high * (1 - settings.trailing_distance_pct)
            pos.stop_loss = max(pos.stop_loss, trail_stop)

        if price <= pos.stop_loss:
            evt = self.portfolio.sell(symbol, price, "손절")
            if evt:
                self.bot.recent_trades = self.portfolio.trades[-20:]
            return

        if price >= pos.take_profit:
            evt = self.portfolio.sell(symbol, price, "익절")
            if evt:
                self.bot.recent_trades = self.portfolio.trades[-20:]
            return

        # emergency cut on sharp dump from entry
        if pnl_pct <= -0.12:
            evt = self.portfolio.sell(symbol, price, "급락 방어")
            if evt:
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
        out = {}
        for sym in self.portfolio.positions:
            t = tickers.get(sym)
            if t:
                out[sym] = float(t["lastPrice"])
        if self.bot.selected_symbol in tickers:
            out[self.bot.selected_symbol] = float(
                tickers[self.bot.selected_symbol]["lastPrice"]
            )
        return out

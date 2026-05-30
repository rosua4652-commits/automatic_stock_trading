import asyncio
import time
from typing import Callable, Optional

from app.engine.live_orders import live_market_buy, live_market_sell
from app.engine.portfolio import PortfolioManager
from app.engine.portfolio_store import store
from app.engine.recommendations import build_recommendations
from app.market.binance import binance
from app.market.coin_registry import coin_meta
from app.market.entry_analyzer import analyze_entry, format_entry_detail
from app.market.scanner import build_ticker_candidates, scan_market, top_usdt_symbols
from app.models import (
    AppConfig,
    BotState,
    BotStatus,
    CoinCandidate,
    CoinMeta,
    CoinView,
    ManualBuyRequest,
    ManualSellRequest,
    RecommendationApplyItem,
    TradeMode,
)
from app.config import settings
from app.storage.credentials import has_api_keys


class TradingEngine:
    def __init__(self) -> None:
        self.config = AppConfig()
        self.portfolio: PortfolioManager = store.paper
        self.bot = BotState()
        self._task: Optional[asyncio.Task] = None
        self._guard_task: Optional[asyncio.Task] = None
        self._listeners: list[Callable[[], None]] = []
        self._status_version: int = 0
        self._link_message: str = ""

    def bind_portfolio(self) -> None:
        """현재 모드에 맞는 포트폴리오만 참조 (시뮬·실거래 분리)."""
        self.portfolio = store.get(self.config.trade_mode)

    def _persist(self) -> None:
        store.persist_active(self.config.trade_mode)

    def _is_live(self) -> bool:
        return self.config.trade_mode == TradeMode.LIVE

    def is_running(self) -> bool:
        return self.bot.status == BotStatus.RUNNING

    def can_manual_trade(self) -> bool:
        return self.bot.status != BotStatus.STOPPING

    def ensure_auto_guard(self) -> None:
        """AI 매수 포지션 익절·손절 — 분석 중지 후에도 주기 감시."""
        if self._guard_task and not self._guard_task.done():
            return
        self._guard_task = asyncio.create_task(self._auto_guard_loop())

    async def _auto_guard_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(5)
                self.bind_portfolio()
                has_auto = any(
                    p.auto_quantity > 1e-10 and not p.excluded_from_auto
                    for p in self.portfolio.positions.values()
                )
                if not has_auto:
                    continue
                try:
                    tickers = await binance.tickers_24h()
                    await self._monitor_positions(tickers)
                    if not self._is_live():
                        self._persist()
                    self._notify()
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass

    def subscribe(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def _notify(self) -> None:
        for cb in self._listeners:
            try:
                cb()
            except Exception:
                pass

    def _bump_version(self) -> int:
        self._status_version += 1
        return self._status_version

    async def start(self) -> tuple[bool, str]:
        if self._is_live():
            if not has_api_keys(self.config):
                self.bot.message = "실거래: API 키를 설정에서 입력하세요"
                return False, self.bot.message
            try:
                self._link_message = await store.sync_live(self.config)
                self.bind_portfolio()
            except Exception as e:
                self.bot.message = f"거래소 연동 실패: {e}"
                return False, self.bot.message

        if self.bot.status == BotStatus.RUNNING:
            return True, "이미 실행 중입니다"

        self.bind_portfolio()
        self._bump_version()
        self.bot.status = BotStatus.RUNNING
        self.bot.manual_mode = True
        self.bot.message = "시장 스캔·차트 분석 중... (승인 후 매수)"
        self._task = asyncio.create_task(self._loop())
        await self._tick()
        self._notify()
        return True, self.bot.message

    async def stop(self) -> None:
        if self.bot.status == BotStatus.STOPPED:
            return

        self._bump_version()
        self.bot.status = BotStatus.STOPPING
        self.bot.message = "분석 중지 중..."
        self._notify()

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._task = None

        self.bot.status = BotStatus.STOPPED
        self.bot.manual_mode = True
        self.bot.message = "분석 중지됨 · 제안 목록에서 승인 매수 또는 수동 매매"
        self._bump_version()
        self._notify()

    async def update_config(self, cfg: AppConfig) -> str:
        old_mode = self.config.trade_mode
        if self.is_running():
            await self.stop()
        self.config = cfg
        switch_msg = await store.on_mode_change(old_mode, cfg.trade_mode, cfg)
        self.bind_portfolio()
        if cfg.trade_mode == TradeMode.PAPER:
            self.portfolio.apply_config(cfg)
            self._persist()
        self._link_message = switch_msg
        self._bump_version()
        self._notify()
        return switch_msg

    async def ensure_candidate_entry(self, symbol: str) -> None:
        """탭에서 선택한 코인 진입 분석이 없으면 보강."""
        sym = symbol.upper()
        cand = next((c for c in self.bot.candidates if c.symbol == sym), None)
        if not cand or cand.entry_detail:
            return
        signal = await analyze_entry(sym, self.config.min_entry_score)
        cand.entry_score = signal.score
        cand.entry_ok = signal.ok
        cand.entry_scalp_ok = signal.scalp_ok
        cand.entry_outlook = signal.outlook
        cand.entry_pattern = signal.pattern
        cand.entry_reasons = signal.reasons
        cand.entry_detail = format_entry_detail(
            signal,
            min_entry_score=self.config.min_entry_score,
            min_market_score=self.config.min_buy_score,
            market_score=cand.score,
        )
        self._notify()

    def set_view_symbol(self, symbol: str) -> str:
        sym = symbol.upper()
        self.bot.view_symbol = sym
        self._notify()
        return sym

    async def manual_buy(self, req: ManualBuyRequest) -> tuple[bool, str]:
        if not self.can_manual_trade():
            return False, "잠시 후 다시 시도하세요."

        self.bind_portfolio()
        self.portfolio.usdt_krw = await binance.usdt_krw_rate()
        symbol = req.symbol.upper()

        if self._is_live():
            ok, msg = await live_market_buy(
                self.config, symbol, req.amount_krw, "수동 매수", as_auto=False
            )
            self.bind_portfolio()
            self.bot.recent_trades = self.portfolio.trades[-30:]
            self._notify()
            return ok, msg

        tickers = await binance.tickers_24h()
        t = tickers.get(symbol)
        if not t:
            return False, "코인 시세를 찾을 수 없습니다"
        price = float(t["lastPrice"])
        base = coin_meta(symbol)["base"]
        sl = self.config.stop_loss_pct / 100
        tp = self.config.take_profit_pct / 100
        est_qty = req.amount_krw / self.portfolio.usdt_krw / max(price, 1e-12)
        pos = self.portfolio.buy(
            symbol,
            base,
            price,
            req.amount_krw,
            sl,
            tp,
            reason=f"수동 매수 · {int(req.amount_krw):,}원",
            entry_reason=(
                f"수동 매수 · ${price:.4f} · {int(req.amount_krw):,}원 · "
                f"예상 수량 {est_qty:.6f}"
            ),
            auto_managed=False,
        )
        if not pos:
            return False, "잔고 부족 또는 최소 금액 미달"
        self._persist()
        self.bot.recent_trades = self.portfolio.trades[-30:]
        self._notify()
        return True, f"{pos.display} 모의 매수 완료"

    async def manual_sell(self, req: ManualSellRequest) -> tuple[bool, str]:
        if not self.can_manual_trade():
            return False, "잠시 후 다시 시도하세요."

        self.bind_portfolio()
        self.portfolio.usdt_krw = await binance.usdt_krw_rate()
        symbol = req.symbol.upper()
        if symbol not in self.portfolio.positions:
            return False, "보유하지 않은 코인입니다"

        if self._is_live():
            ok, msg = await live_market_sell(
                self.config,
                symbol,
                req.percent,
                "수동 매도",
                auto_only=getattr(req, "from_auto_only", False),
            )
            self.bind_portfolio()
            self.bot.recent_trades = self.portfolio.trades[-30:]
            self._notify()
            return ok, msg

        tickers = await binance.tickers_24h()
        t = tickers.get(symbol)
        if not t:
            return False, "시세 조회 실패"
        price = float(t["lastPrice"])
        pos = self.portfolio.positions[symbol]
        evt = self.portfolio.sell(symbol, price, "수동 매도", req.percent)
        if not evt:
            return False, "매도 실패"
        self._persist()
        self.bot.recent_trades = self.portfolio.trades[-30:]
        self._notify()
        return True, f"{pos.display} 모의 {req.percent:.0f}% 매도"

    async def manual_sell_all(self, percent: float = 100.0) -> tuple[bool, str]:
        if not self.can_manual_trade():
            return False, "잠시 후 다시 시도하세요."

        self.bind_portfolio()
        symbols = list(self.portfolio.positions.keys())
        if not symbols:
            return False, "보유 코인이 없습니다."

        ok_count = 0
        fail_msgs: list[str] = []
        for sym in symbols:
            ok, msg = await self.manual_sell(
                ManualSellRequest(symbol=sym, percent=percent)
            )
            if ok:
                ok_count += 1
            else:
                fail_msgs.append(msg)

        if ok_count == 0:
            return False, fail_msgs[0] if fail_msgs else "전체 매도 실패"

        pct_label = f"{percent:.0f}%"
        if fail_msgs:
            return (
                True,
                f"{ok_count}종목 {pct_label} 매도 · 실패 {len(fail_msgs)}건",
            )
        return True, f"보유 {ok_count}종목 {pct_label} 전체 매도 완료"

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
                interval = max(15, self.config.scan_interval_sec)
                for tick in range(interval):
                    if not self.is_running():
                        return
                    if tick > 0 and tick % 5 == 0:
                        try:
                            self.bind_portfolio()
                            tix = await binance.tickers_24h()
                            await self._monitor_positions(tix)
                            if self._is_live():
                                self.bind_portfolio()
                            else:
                                self._persist()
                            self._notify()
                        except Exception:
                            pass
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            if self.bot.status != BotStatus.STOPPED:
                self.bot.status = BotStatus.STOPPED
                self.bot.manual_mode = True
                self.bot.message = "분석이 중지되었습니다"
            self._task = None
            self._bump_version()

    async def _tick(self) -> None:
        if not self.is_running():
            return

        self.bind_portfolio()
        if self._is_live():
            try:
                self._link_message = await store.sync_live(self.config)
                self.bind_portfolio()
            except Exception as e:
                self.bot.message = f"연동 오류: {e}"
                return

        self.portfolio.usdt_krw = await binance.usdt_krw_rate()
        from app.config import settings as app_settings

        tickers = await binance.tickers_24h()
        self.bot.liquid_symbols = await top_usdt_symbols(
            app_settings.tab_symbol_limit, is_running=self.is_running
        )
        if not self.is_running():
            return
        deep = await scan_market(is_running=self.is_running)
        if not self.is_running():
            return

        deep_syms = {c.symbol for c in deep}
        quick_syms = [s for s in self.bot.liquid_symbols if s not in deep_syms]
        quick = await build_ticker_candidates(quick_syms, tickers)
        by_sym: dict[str, CoinCandidate] = {c.symbol: c for c in deep}
        for c in quick:
            by_sym.setdefault(c.symbol, c)
        candidates = list(by_sym.values())

        sem = asyncio.Semaphore(14)

        async def enrich(cand: CoinCandidate):
            if not self.is_running():
                return cand, None
            async with sem:
                signal = await analyze_entry(cand.symbol, self.config.min_entry_score)
            cand.entry_score = signal.score
            cand.entry_ok = signal.ok
            cand.entry_scalp_ok = signal.scalp_ok
            cand.entry_outlook = signal.outlook
            cand.entry_pattern = signal.pattern
            cand.entry_reasons = signal.reasons
            cand.entry_detail = format_entry_detail(
                signal,
                min_entry_score=self.config.min_entry_score,
                min_market_score=self.config.min_buy_score,
                market_score=cand.score,
            )
            return cand, signal if signal.ok else None

        results = await asyncio.gather(*[enrich(c) for c in candidates])
        enriched = [(c, s) for c, s in results if s is not None]
        enriched.sort(key=lambda x: x[0].score, reverse=True)

        self.bot.candidates = sorted(
            candidates,
            key=lambda c: (c.entry_ok, c.entry_scalp_ok, c.score),
            reverse=True,
        )
        self.bot.last_scan = time.time()

        held = {
            s
            for s, p in self.portfolio.positions.items()
            if p.quantity > 1e-10
        }
        snap = self.portfolio.snapshot({}, self.config)
        self.bot.recommendations = build_recommendations(
            candidates,
            snap.cash_krw,
            self.config,
            held,
            tickers=tickers,
            usdt_krw=self.portfolio.usdt_krw,
        )
        mode = "모의" if self.config.trade_mode == TradeMode.PAPER else "실거래"
        total_rec = sum(r.amount_krw for r in self.bot.recommendations)
        scalp_only = sum(
            1 for c in candidates if c.entry_scalp_ok and not c.entry_ok
        )
        scalp_total = len(enriched) + scalp_only
        self.bot.message = (
            f"[{mode}] 분석 {len(candidates)}종 · 자동추천 {len(enriched)}종 · "
            f"단타가능 {scalp_total}종 · "
            f"제안 {len(self.bot.recommendations)}건 · 합계 {total_rec:,.0f}원"
        )
        await self._monitor_positions(tickers)
        if not self._is_live():
            self._persist()
        self._notify()

    async def _monitor_positions(self, tickers: dict) -> None:
        """보유 AI(auto) 포지션 손절·익절·트레일링 — 분석 중·중지 후 모두."""
        if not self.portfolio.positions:
            return
        for sym in list(self.portfolio.positions.keys()):
            pos = self.portfolio.positions.get(sym)
            if (
                not pos
                or pos.auto_quantity <= 1e-10
                or pos.excluded_from_auto
            ):
                continue
            t = tickers.get(sym)
            if not t:
                continue
            await self._manage_position(sym, float(t["lastPrice"]))

    async def apply_recommendations(
        self,
        symbols: list[str],
        items: list[RecommendationApplyItem] | None = None,
    ) -> tuple[bool, str]:
        """사용자 승인 후 제안 매수 실행 (금액 조절 가능, 익절·손절 자동)."""
        self.bind_portfolio()
        self.portfolio.usdt_krw = await binance.usdt_krw_rate()

        if not self.bot.recommendations:
            return False, "먼저 「분석 시작」으로 투자 제안을 받으세요"

        amount_map: dict[str, float] = {}
        if items:
            for it in items:
                if isinstance(it, RecommendationApplyItem):
                    amount_map[it.symbol.upper()] = float(it.amount_krw)
                elif isinstance(it, dict):
                    amount_map[str(it["symbol"]).upper()] = float(it["amount_krw"])

        want = {s.upper() for s in symbols} if symbols else None
        to_apply = [
            r
            for r in self.bot.recommendations
            if r.selected and (want is None or r.symbol.upper() in want)
        ]
        if not to_apply:
            return False, "매수할 코인을 선택하세요"

        tickers = await binance.tickers_24h()
        sl_pct = self.config.stop_loss_pct / 100
        tp_pct = self.config.take_profit_pct / 100
        ok_n = 0
        fail_msgs: list[str] = []
        success_syms: set[str] = set()

        for rec in to_apply:
            sym = rec.symbol.upper()
            t = tickers.get(sym)
            if not t:
                fail_msgs.append(f"{rec.base}: 시세 없음")
                continue
            price = float(t["lastPrice"])
            entry_txt = rec.entry_detail or "승인 매수"
            amt = round(
                max(settings.min_buy_krw, amount_map.get(sym, rec.amount_krw)), -3
            )
            tp_label = f"익절{self.config.take_profit_pct:g}%"
            sl_label = f"손절{self.config.stop_loss_pct:g}%"
            buy_reason = (
                f"AI 승인 · {int(amt):,}원 · {tp_label}/{sl_label} 자동"
            )

            if self._is_live():
                ok, msg = await live_market_buy(
                    self.config,
                    sym,
                    amt,
                    f"{buy_reason} · {entry_txt}",
                    as_auto=True,
                )
                if ok:
                    ok_n += 1
                    success_syms.add(sym)
                    self.bind_portfolio()
                else:
                    fail_msgs.append(f"{rec.base}: {msg}")
            else:
                pos = self.portfolio.buy(
                    sym,
                    rec.base,
                    price,
                    amt,
                    sl_pct,
                    tp_pct,
                    score=rec.market_score,
                    reason=buy_reason,
                    entry_reason=f"{entry_txt} · {tp_label}/{sl_label} 자동매도",
                    entry_score=rec.entry_score,
                    entry_outlook="AI 자동투자",
                    auto_managed=True,
                )
                if pos:
                    ok_n += 1
                    success_syms.add(sym)
                else:
                    fail_msgs.append(f"{rec.base}: 잔고 부족")

        if ok_n:
            await self._monitor_positions(tickers)
            self._persist()
            self.bot.recent_trades = self.portfolio.trades[-40:]
            self.bot.recommendations = [
                r for r in self.bot.recommendations if r.symbol.upper() not in success_syms
            ]
            self.ensure_auto_guard()
        self._bump_version()
        self._notify()

        if ok_n == 0:
            return False, fail_msgs[0] if fail_msgs else "매수 실패"
        tail = f" ({fail_msgs[0]})" if fail_msgs else ""
        return (
            True,
            f"{ok_n}건 AI 자동투자 매수 · 익절/손절 감시 중{tail}",
        )

    async def set_position_exclude(self, symbol: str, exclude: bool) -> tuple[bool, str]:
        self.bind_portfolio()
        sym = symbol.upper()
        pos = self.portfolio.set_exclude(sym, exclude)
        if not pos:
            return False, "보유하지 않은 코인입니다"
        self._persist()
        if self._is_live():
            await store.sync_live(self.config)
            self.bind_portfolio()
        if exclude:
            return True, f"{pos.display} — 수동 보유 (AI는 auto 수량만 관리)"
        return True, f"{pos.display} — 자동투자 예외 해제"

    async def _manage_position(self, symbol: str, price: float) -> None:
        pos = self.portfolio.positions.get(symbol)
        if (
            not pos
            or pos.auto_quantity <= 0
            or pos.excluded_from_auto
        ):
            return

        pos.current_price = price
        if pos.trailing_high <= 0:
            pos.trailing_high = price
        if price > pos.trailing_high:
            pos.trailing_high = price

        pnl_pct = (price - pos.auto_avg_price) / pos.auto_avg_price if pos.auto_avg_price else 0

        from app.config import settings

        if pnl_pct >= settings.trailing_activate_pct:
            trail_stop = pos.trailing_high * (1 - settings.trailing_distance_pct)
            if pos.stop_loss > 0:
                pos.stop_loss = max(pos.stop_loss, trail_stop)

        if pos.stop_loss > 0 and price <= pos.stop_loss:
            await self._auto_sell(symbol, "손절")
            return

        if pos.take_profit > 0 and price >= pos.take_profit:
            await self._auto_sell(symbol, "익절")
            return

        if pnl_pct <= -0.12:
            await self._auto_sell(symbol, "급락 방어")

    async def _auto_sell(self, symbol: str, reason: str) -> None:
        if self._is_live():
            ok, _ = await live_market_sell(
                self.config, symbol, 100.0, reason, auto_only=True
            )
            if ok:
                self.bind_portfolio()
                self.bot.recent_trades = self.portfolio.trades[-30:]
        else:
            tickers = await binance.tickers_24h()
            t = tickers.get(symbol)
            px = float(t["lastPrice"]) if t else 0
            if self.portfolio.sell(symbol, px, reason, auto_only=True):
                self._persist()
                self.bot.recent_trades = self.portfolio.trades[-30:]

    async def get_candles(self, symbol: str, interval: str = "1h") -> list[dict]:
        iv = interval.lower()
        limits = {"1s": 300, "1m": 500, "15m": 300, "1h": 200, "4h": 200, "1d": 200}
        limit = limits.get(iv, 200)
        raw = await binance.klines(symbol, iv, limit)
        candles = [
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
        candles.sort(key=lambda c: c["time"])
        seen: set[int] = set()
        unique: list[dict] = []
        for c in candles:
            if c["time"] not in seen:
                seen.add(c["time"])
                unique.append(c)
        return unique

    async def tab_quotes_map(self, limit: int = 120) -> dict[str, dict]:
        """탭 UI용 시세 (USDT·원화·24h)."""
        tickers = await binance.tickers_24h()
        self.bind_portfolio()
        rate = self.portfolio.usdt_krw
        if rate <= 0:
            rate = await binance.usdt_krw_rate()
            self.portfolio.usdt_krw = rate
        out: dict[str, dict] = {}
        for sym in self.tab_symbols()[:limit]:
            t = tickers.get(sym)
            if not t:
                continue
            px = float(t.get("lastPrice", 0))
            if px <= 0:
                continue
            out[sym] = {
                "price_usdt": px,
                "price_krw": round(px * rate),
                "change_24h": float(t.get("priceChangePercent", 0)),
            }
        return out

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
        majors = (
            "BTCUSDT",
            "ETHUSDT",
            "SOLUSDT",
            "XRPUSDT",
            "BNBUSDT",
            "DOGEUSDT",
            "ADAUSDT",
            "AVAXUSDT",
            "LINKUSDT",
            "SUIUSDT",
        )
        seen: set[str] = set()
        tabs: list[str] = [self.bot.view_symbol]
        seen.add(self.bot.view_symbol)
        for sym in self.portfolio.positions:
            if sym not in seen:
                tabs.append(sym)
                seen.add(sym)
        for sym in self.bot.liquid_symbols:
            if sym not in seen:
                tabs.append(sym)
                seen.add(sym)
        for sym in majors:
            if sym not in seen:
                tabs.append(sym)
                seen.add(sym)
        for c in self.bot.candidates:
            if c.symbol not in seen:
                tabs.append(c.symbol)
                seen.add(c.symbol)
        return tabs

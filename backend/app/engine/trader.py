import asyncio
import time
from typing import Callable, Optional

from app.engine.exit_rules import (
    config_exit_triggered,
    custom_exit_triggered,
)
from app.engine.live_orders import live_market_buy, live_market_sell
from app.engine.portfolio import PortfolioManager
from app.engine.portfolio_store import store
from app.engine.recommendations import build_recommendations, cap_apply_amounts
from app.market.upbit_data import market
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


def _fmt_pct_setting(n: float) -> str:
    v = round(float(n), 2)
    text = f"{v:.2f}".rstrip("0").rstrip(".")
    return f"{text}%"


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
        self.portfolio.trading_fee_pct = float(
            getattr(self.config, "trading_fee_pct", 0.05)
        )
        if self._repair_auto_positions() and not self._is_live():
            self._persist()

    def _repair_auto_positions(self) -> bool:
        """예전 데이터: AI 매수인데 auto_quantity 가 비어 있으면 복구."""
        sl = self.config.stop_loss_pct / 100
        tp = self.config.take_profit_pct / 100
        changed = False
        for pos in self.portfolio.positions.values():
            if pos.auto_quantity > 1e-12:
                continue
            if pos.excluded_from_auto:
                continue
            hint = f"{pos.entry_outlook} {pos.entry_reason}"
            if not any(
                k in hint
                for k in ("AI", "승인", "자동투자", "auto", "익절", "손절")
            ):
                continue
            if pos.quantity <= 0:
                continue
            pos.auto_quantity = pos.quantity
            pos.manual_quantity = 0.0
            px = pos.avg_price or pos.current_price
            if px > 0:
                pos.auto_avg_price = px
                pos.auto_cost_basis_krw = pos.cost_basis_krw
                if pos.take_profit <= 0:
                    pos.take_profit = px * (1 + tp)
                if pos.stop_loss <= 0:
                    pos.stop_loss = px * (1 - sl)
                if pos.trailing_high <= 0:
                    pos.trailing_high = px
            changed = True
        return changed

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
                await asyncio.sleep(3)
                self.bind_portfolio()
                has_watch = any(
                    p.quantity > 1e-12
                    and (
                        p.custom_sl_tp
                        or (p.auto_quantity > 1e-10 and not p.excluded_from_auto)
                        or p.manual_quantity > 1e-10
                    )
                    for p in self.portfolio.positions.values()
                )
                if not has_watch:
                    continue
                try:
                    tickers = await market.tickers_24h()
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
        self.ensure_auto_guard()
        try:
            tickers = await market.tickers_24h()
            await self._monitor_positions(tickers)
            if not self._is_live():
                self._persist()
        except Exception:
            pass
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
        self.portfolio.usdt_krw = await market.usdt_krw_rate()
        symbol = req.symbol.upper()

        if self._is_live():
            ok, msg = await live_market_buy(
                self.config, symbol, req.amount_krw, "수동 매수", as_auto=False
            )
            self.bind_portfolio()
            self.bot.recent_trades = self.portfolio.trades[-30:]
            self._notify()
            return ok, msg

        tickers = await market.tickers_24h()
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
        self.portfolio.usdt_krw = await market.usdt_krw_rate()
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

        tickers = await market.tickers_24h()
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
                            tix = await market.tickers_24h()
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

        self.portfolio.usdt_krw = await market.usdt_krw_rate()
        from app.config import settings as app_settings

        tickers = await market.tickers_24h()
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

    async def _price_for_symbol(self, sym: str, tickers: dict) -> float:
        t = tickers.get(sym)
        if t:
            return float(t.get("lastPrice") or 0)
        pos = self.portfolio.positions.get(sym)
        if pos and pos.current_price > 0:
            return pos.current_price
        try:
            raw = await market.klines(sym, "1m", 5)
            if raw:
                return float(raw[-1][4])
        except Exception:
            pass
        return 0.0

    async def _monitor_positions(self, tickers: dict) -> None:
        """보유 포지션 손절·익절 (수동 지정가 / AI·설정 %)."""
        if not self.portfolio.positions:
            return
        for sym in list(self.portfolio.positions.keys()):
            pos = self.portfolio.positions.get(sym)
            if not pos or pos.quantity <= 1e-12:
                continue
            price = await self._price_for_symbol(sym, tickers)
            if price <= 0:
                continue
            await self._manage_exit(sym, price)

    async def _manage_exit(self, symbol: str, price: float) -> bool:
        """손익절 조건이면 매도 실행. True=매도 성공."""
        pos = self.portfolio.positions.get(symbol)
        if not pos:
            return False
        if price > 0:
            pos.current_price = price
            rate = max(self.portfolio.usdt_krw, 1.0)
            if getattr(pos, "data_source", "") == "upbit":
                pos.current_price_krw = price * rate

        rate = max(self.portfolio.usdt_krw, 1.0)

        if pos.custom_sl_tp:
            hit, reason = custom_exit_triggered(
                pos, price, rate, self.config
            )
            if hit:
                return await self._auto_sell(symbol, reason, full=True)
            return False

        if pos.auto_quantity > 1e-10 and not pos.excluded_from_auto:
            await self._manage_position(symbol, price)
            return False

        hit, reason = config_exit_triggered(pos, price, rate, self.config)
        if hit:
            return await self._auto_sell(symbol, reason, full=True)
        return False

    async def _try_immediate_exit_on_apply(self, symbol: str) -> str | None:
        """손익절 적용 직후 — 이미 범위 안이면 즉시 매도."""
        sym = symbol.upper()
        pos = self.portfolio.positions.get(sym)
        if not pos or pos.quantity <= 1e-12:
            return None

        if self.portfolio.usdt_krw <= 0:
            self.portfolio.usdt_krw = await market.usdt_krw_rate()

        tickers = await market.tickers_for_symbols([sym])
        price = await self._price_for_symbol(sym, tickers)
        if price <= 0 and pos.current_price > 0:
            price = pos.current_price
        if price <= 0 and pos.current_price_krw > 0 and self.portfolio.usdt_krw > 0:
            price = pos.current_price_krw / self.portfolio.usdt_krw
        if price <= 0:
            return None

        rate = max(self.portfolio.usdt_krw, 1.0)
        if pos.custom_sl_tp:
            hit, reason = custom_exit_triggered(pos, price, rate, self.config)
        else:
            hit, reason = config_exit_triggered(pos, price, rate, self.config)
        if not hit:
            return None

        qty_before = pos.quantity
        sold = await self._auto_sell(sym, reason, full=True)
        self.bind_portfolio()

        if self._is_live():
            await store.sync_live(self.config)
            self.bind_portfolio()
        else:
            self._persist()

        pos_after = self.portfolio.positions.get(sym)
        if not sold or (pos_after and pos_after.quantity >= qty_before * 0.99):
            fail = (self.bot.message or "").strip()
            if fail:
                return fail
            return (
                f"{pos.display} — 손익절 범위이나 매도 실패 "
                "(API·최소주문·잔고 확인)"
            )

        self.bot.recent_trades = self.portfolio.trades[-30:]
        self._bump_version()
        self._notify()
        return f"{pos.display} — 현재가가 손익절 범위 안 · 즉시 전량 매도 완료"

    async def apply_recommendations(
        self,
        symbols: list[str],
        items: list[RecommendationApplyItem] | None = None,
    ) -> tuple[bool, str]:
        """사용자 승인 후 제안 매수 실행 (금액 조절 가능, 익절·손절 자동)."""
        self.bind_portfolio()
        self.portfolio.usdt_krw = await market.usdt_krw_rate()

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

        raw_amts: dict[str, float] = {}
        for rec in to_apply:
            sym = rec.symbol.upper()
            raw_amts[sym] = float(amount_map.get(sym, rec.amount_krw))
        fee_pct = float(getattr(self.config, "trading_fee_pct", 0.05))
        capped_amts = cap_apply_amounts(raw_amts, self.portfolio.cash_krw, fee_pct)
        if not capped_amts:
            return False, "현금이 부족해 승인 매수할 수 없습니다"

        tickers = await market.tickers_24h()
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
            if sym not in capped_amts:
                fail_msgs.append(f"{rec.base}: 배분 제외(현금 부족)")
                continue
            amt = round(capped_amts[sym], -3)
            tp_label = f"익절{_fmt_pct_setting(self.config.take_profit_pct)}"
            sl_label = f"손절{_fmt_pct_setting(self.config.stop_loss_pct)}"
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
                    score=rec.market_score,
                    entry_score=rec.entry_score,
                    entry_reason=f"{entry_txt} · {tp_label}/{sl_label} 자동매도",
                    entry_outlook="AI 자동투자",
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

    async def set_position_exit_plan(
        self,
        symbol: str,
        *,
        custom_sl_tp: bool,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        stop_loss_usdt: float | None = None,
        take_profit_usdt: float | None = None,
    ) -> tuple[bool, str]:
        self.bind_portfolio()
        sym = symbol.upper()
        pos = self.portfolio.set_exit_plan(
            sym,
            custom_sl_tp=custom_sl_tp,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            stop_loss_usdt=stop_loss_usdt,
            take_profit_usdt=take_profit_usdt,
            config=self.config,
        )
        if not pos:
            return False, "보유하지 않은 코인입니다"
        self._persist()
        self.ensure_auto_guard()

        immediate = await self._try_immediate_exit_on_apply(sym)
        if immediate:
            if "즉시 전량 매도 완료" in immediate:
                return True, immediate
            return False, immediate

        if self._is_live():
            await store.sync_live(self.config)
            self.bind_portfolio()
            pos = self.portfolio.positions.get(sym) or pos
            immediate2 = await self._try_immediate_exit_on_apply(sym)
            if immediate2:
                if "즉시 전량 매도 완료" in immediate2:
                    return True, immediate2
                return False, immediate2

        if not self._is_live():
            self._persist()

        if custom_sl_tp:
            sl_p = pos.custom_stop_loss_pct or self.config.stop_loss_pct
            tp_p = pos.custom_take_profit_pct or self.config.take_profit_pct
            return (
                True,
                f"{pos.display} — 손절 -{sl_p:g}% / 익절 +{tp_p:g}% 적용 · "
                f"범위 도달 시 자동 매도 (감시 중)",
            )
        return (
            True,
            f"{pos.display} — 설정 손절 {self.config.stop_loss_pct}% / "
            f"익절 {self.config.take_profit_pct}% 자동 감시",
        )

    async def _manage_position(self, symbol: str, price: float) -> None:
        pos = self.portfolio.positions.get(symbol)
        if (
            not pos
            or pos.auto_quantity <= 0
            or pos.excluded_from_auto
        ):
            return

        entry = pos.auto_avg_price
        if entry <= 0:
            entry = pos.avg_price
            if entry > 0:
                pos.auto_avg_price = entry

        pos.current_price = price
        if pos.trailing_high <= 0:
            pos.trailing_high = price
        if price > pos.trailing_high:
            pos.trailing_high = price

        tp_ratio = self.config.take_profit_pct / 100
        sl_ratio = self.config.stop_loss_pct / 100
        if entry > 0 and not pos.custom_sl_tp:
            pos.take_profit = entry * (1 + tp_ratio)
            base_sl = entry * (1 - sl_ratio)
            if pos.stop_loss <= 0:
                pos.stop_loss = base_sl

        auto_pnl = (price - entry) / entry if entry > 0 else 0.0

        from app.config import settings

        if auto_pnl >= settings.trailing_activate_pct:
            trail_stop = pos.trailing_high * (1 - settings.trailing_distance_pct)
            if pos.stop_loss > 0:
                pos.stop_loss = max(pos.stop_loss, trail_stop)

        # 설정 % 기준 (화면 수익률과 동일) + 가격선 이중 확인
        if entry > 0 and auto_pnl <= -sl_ratio:
            await self._auto_sell(symbol, "손절")
            return

        if entry > 0 and (
            auto_pnl >= tp_ratio
            or (pos.take_profit > 0 and price >= pos.take_profit * 0.9999)
        ):
            await self._auto_sell(symbol, "익절")
            return

        if auto_pnl <= -0.12:
            await self._auto_sell(symbol, "급락 방어")

    async def _auto_sell(self, symbol: str, reason: str, *, full: bool = False) -> bool:
        sym = symbol.upper()
        if self._is_live():
            ok, msg = await live_market_sell(
                self.config,
                sym,
                100.0,
                reason,
                auto_only=not full,
            )
            if ok:
                self.bind_portfolio()
                self.bot.recent_trades = self.portfolio.trades[-30:]
                self.bot.message = f"{sym} {reason} 자동 매도 완료"
                self._bump_version()
                self._notify()
                return True
            self.bot.message = f"{sym} {reason} 자동 매도 실패: {msg}"
            self._notify()
            return False
        tickers = await market.tickers_for_symbols([sym])
        px = await self._price_for_symbol(sym, tickers)
        if px <= 0:
            pos = self.portfolio.positions.get(sym)
            px = pos.current_price if pos else 0.0
        if px > 0 and self.portfolio.sell(sym, px, reason, auto_only=not full):
            self._persist()
            self.bot.recent_trades = self.portfolio.trades[-30:]
            self.bot.message = f"{sym} {reason} 자동 매도 완료"
            self._bump_version()
            self._notify()
            return True
        self.bot.message = f"{sym} {reason} 자동 매도 실패 (시세 없음)"
        self._notify()
        return False

    async def get_candles(self, symbol: str, interval: str = "1h") -> list[dict]:
        iv = interval.lower()
        limits = {"1s": 300, "1m": 500, "15m": 300, "1h": 200, "4h": 200, "1d": 200}
        limit = limits.get(iv, 200)
        try:
            raw = await market.klines(symbol, iv, limit)
        except Exception:
            raw = market.get_cached_klines(symbol, iv) or []
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
        syms = self.tab_symbols()[:limit]
        tickers = await market.tickers_for_symbols(syms)
        self.bind_portfolio()
        rate = self.portfolio.usdt_krw
        if rate <= 0:
            rate = await market.usdt_krw_rate()
            self.portfolio.usdt_krw = rate
        out: dict[str, dict] = {}
        for sym in syms:
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
        need = list(self.portfolio.positions.keys())
        sym = self.bot.view_symbol
        if sym and sym not in need:
            need.append(sym)
        tickers = await market.tickers_for_symbols(need)
        out: dict[str, float] = {}
        for s, t in tickers.items():
            if t:
                out[s] = float(t["lastPrice"])
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
            if pos.data_source == "upbit" and pos.current_price_krw > 0:
                rate = self.portfolio.usdt_krw or 1350.0
                price = pos.current_price_krw / max(rate, 1.0)
            else:
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

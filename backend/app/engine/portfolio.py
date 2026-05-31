import time
from typing import Optional

from app.config import settings
from app.market.coin_registry import coin_meta
from app.models import AppConfig, ChartMarker, PortfolioSnapshot, Position, TradeEvent


class PortfolioManager:
    def __init__(self) -> None:
        self.cash_krw = settings.initial_balance_krw
        self.realized_pnl_krw = 0.0
        self.positions: dict[str, Position] = {}
        self.trades: list[TradeEvent] = []
        self.usdt_krw = 1350.0
        self.trading_fee_pct = 0.05

    def apply_config(self, config: AppConfig) -> None:
        self.trading_fee_pct = float(getattr(config, "trading_fee_pct", 0.05))
        if not self.positions and not self.trades:
            self.cash_krw = config.initial_balance_krw
            self.realized_pnl_krw = 0.0

    def _fee_krw(self, amount_krw: float) -> float:
        rate = getattr(self, "trading_fee_pct", 0.05) / 100
        return amount_krw * rate

    def _sell_cash_flow(
        self,
        sell_qty: float,
        price_usdt: float,
        avg_price_usdt: float,
        cost_portion_krw: float,
        *,
        charge_fee: bool = True,
    ) -> tuple[float, float]:
        """
        매도 현금·실현손익 (원).
        같은 USDT 가격이면 환율 변동만으로 손실이 나지 않도록 USDT 가격 차이만 반영.
        """
        if avg_price_usdt <= 0:
            avg_price_usdt = price_usdt
        usdt_gain = sell_qty * (price_usdt - avg_price_usdt)
        market_pnl_krw = self.usdt_to_krw(usdt_gain)
        proceeds_krw = cost_portion_krw + market_pnl_krw
        fee = self._fee_krw(proceeds_krw) if charge_fee else 0.0
        proceeds_krw -= fee
        realized_delta = market_pnl_krw - fee
        return proceeds_krw, realized_delta

    def set_fx(self, rate: float) -> None:
        self.usdt_krw = rate

    def usdt_to_krw(self, usdt: float) -> float:
        return usdt * self.usdt_krw

    def krw_to_usdt(self, krw: float) -> float:
        return krw / self.usdt_krw

    def _recalc_avg(self, pos: Position) -> None:
        q = pos.quantity
        if q <= 0:
            pos.avg_price = 0.0
            return
        total_cost_usdt = pos.auto_avg_price * pos.auto_quantity + pos.manual_avg_price * pos.manual_quantity
        pos.avg_price = total_cost_usdt / q

    def _trade_event(
        self,
        meta: dict,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        reason: str,
        is_auto: bool,
        *,
        price_krw: float = 0.0,
        amount_krw: float | None = None,
    ) -> TradeEvent:
        amount_usdt = price * quantity
        amt_krw = amount_krw
        if amt_krw is None:
            amt_krw = self.usdt_to_krw(amount_usdt)
        px_krw = price_krw
        if px_krw <= 0 and quantity > 1e-12 and amt_krw > 0:
            px_krw = amt_krw / quantity
        elif px_krw <= 0 and price > 0:
            px_krw = self.usdt_to_krw(price)
        return TradeEvent(
            ts=time.time(),
            symbol=symbol,
            base=meta["base"],
            display=meta["display"],
            side=side,
            price=price,
            price_krw=round(px_krw, 4) if px_krw > 0 else 0.0,
            quantity=quantity,
            amount_krw=round(amt_krw, 0),
            amount_usdt=round(amount_usdt, 4),
            reason=reason,
            is_auto=is_auto,
        )

    def chart_markers(self, symbol: str) -> list[ChartMarker]:
        out: list[ChartMarker] = []
        for t in self.trades:
            if t.symbol != symbol:
                continue
            out.append(
                ChartMarker(
                    time=int(t.ts),
                    price=t.price,
                    side=t.side,
                    text=f"{'AI' if t.is_auto else '수동'}{'매수' if t.side == 'BUY' else '매도'}",
                    is_auto=t.is_auto,
                )
            )
        return out

    @staticmethod
    def position_snap(pos: Optional[Position]) -> dict[str, float]:
        if not pos:
            return {
                "total": 0.0,
                "auto": 0.0,
                "manual": 0.0,
                "auto_cost": 0.0,
                "man_cost": 0.0,
                "cost": 0.0,
            }
        return {
            "total": pos.quantity,
            "auto": pos.auto_quantity,
            "manual": pos.manual_quantity,
            "auto_cost": pos.auto_cost_basis_krw,
            "man_cost": pos.manual_cost_basis_krw,
            "cost": pos.cost_basis_krw,
        }

    def apply_live_buy_after_sync(
        self,
        pos: Position,
        before: dict[str, float],
        delta_qty: float,
        fill_price_usdt: float,
        amount_krw: float,
        auto_managed: bool,
        config: AppConfig,
        *,
        reason: str = "",
        entry_reason: str = "",
        entry_score: float = 0,
        score: float = 0,
        entry_outlook: str = "",
    ) -> None:
        """실거래 체결 후 포지션 메타 — 모의투자 buy()와 동일 규칙."""
        delta = max(0.0, delta_qty)
        if auto_managed:
            new_auto = min(pos.quantity, before["auto"] + delta)
            pos.auto_quantity = new_auto
            pos.manual_quantity = max(0.0, pos.quantity - new_auto)
            pos.excluded_from_auto = False
            pos.auto_cost_basis_krw = before["auto_cost"] + amount_krw
            if pos.auto_quantity > 0:
                pos.auto_avg_price = (
                    pos.auto_cost_basis_krw / self.usdt_krw / pos.auto_quantity
                )
            sl = config.stop_loss_pct / 100
            tp = config.take_profit_pct / 100
            pos.stop_loss = fill_price_usdt * (1 - sl)
            pos.take_profit = fill_price_usdt * (1 + tp)
            pos.trailing_high = max(pos.trailing_high or 0.0, fill_price_usdt)
            pos.entry_reason = entry_reason or reason
            pos.entry_score = entry_score
            pos.score = score
            pos.entry_outlook = entry_outlook or "AI 자동투자"
        else:
            pos.auto_quantity = min(before["auto"], pos.quantity)
            new_manual = min(pos.quantity - pos.auto_quantity, before["manual"] + delta)
            pos.manual_quantity = max(0.0, new_manual)
            pos.manual_cost_basis_krw = before["man_cost"] + amount_krw
            if pos.manual_quantity > 0:
                pos.manual_avg_price = (
                    pos.manual_cost_basis_krw / self.usdt_krw / pos.manual_quantity
                )
            pos.stop_loss = 0.0
            pos.take_profit = 0.0
            pos.trailing_high = 0.0
            pos.entry_reason = entry_reason or reason
            pos.excluded_from_auto = False
        pos.cost_basis_krw = pos.auto_cost_basis_krw + pos.manual_cost_basis_krw
        self._recalc_avg(pos)

    def apply_live_sell_after_sync(
        self,
        pos: Optional[Position],
        before: dict[str, float],
        executed_qty: float,
        fill_price_usdt: float,
        auto_only: bool,
        *,
        charge_fee: bool = False,
    ) -> float:
        """실거래 매도 후 메타·실현손익 — 모의투자 sell()과 동일 규칙. 반환: 실현손익(원)."""
        sell_qty = max(0.0, executed_qty)
        if sell_qty <= 1e-12:
            return 0.0

        sym = pos.symbol if pos else ""

        if auto_only:
            base_qty = before["auto"]
            avg_auto = (
                before["auto_cost"] / self.usdt_krw / base_qty
                if base_qty > 0 and before["auto_cost"] > 0
                else fill_price_usdt
            )
            if base_qty <= 1e-12:
                return 0.0
            sq = min(sell_qty, base_qty)
            cost_portion = before["auto_cost"] * (sq / base_qty)
            _, pnl = self._sell_cash_flow(
                sq, fill_price_usdt, avg_auto, cost_portion, charge_fee=charge_fee
            )
            if pos:
                pos.auto_quantity = max(0.0, min(pos.quantity, base_qty - sq))
                pos.auto_cost_basis_krw = max(0.0, before["auto_cost"] - cost_portion)
                if pos.auto_quantity <= 1e-12:
                    pos.auto_quantity = 0.0
                    pos.auto_cost_basis_krw = 0.0
                    pos.auto_avg_price = 0.0
                    pos.stop_loss = 0.0
                    pos.take_profit = 0.0
                    pos.trailing_high = 0.0
        else:
            total_q = before["total"]
            if total_q <= 1e-12:
                return 0.0
            sq = min(sell_qty, total_q)
            cost_portion = before["cost"] * (sq / total_q)
            avg_all = (
                before["cost"] / self.usdt_krw / total_q
                if total_q > 0
                else fill_price_usdt
            )
            _, pnl = self._sell_cash_flow(
                sq, fill_price_usdt, avg_all, cost_portion, charge_fee=charge_fee
            )
            if pos:
                auto_part = min(sq, before["auto"])
                man_part = sq - auto_part
                if auto_part > 0 and before["auto"] > 0:
                    cost_a = before["auto_cost"] * (auto_part / before["auto"])
                    pos.auto_quantity = max(0.0, before["auto"] - auto_part)
                    pos.auto_cost_basis_krw = max(0.0, before["auto_cost"] - cost_a)
                    if pos.auto_quantity <= 1e-12:
                        pos.auto_quantity = 0.0
                        pos.auto_cost_basis_krw = 0.0
                        pos.auto_avg_price = 0.0
                if man_part > 0 and before["manual"] > 0:
                    cost_m = before["man_cost"] * (man_part / before["manual"])
                    pos.manual_quantity = max(0.0, before["manual"] - man_part)
                    pos.manual_cost_basis_krw = max(0.0, before["man_cost"] - cost_m)
                    if pos.manual_quantity <= 1e-12:
                        pos.manual_quantity = 0.0
                        pos.manual_cost_basis_krw = 0.0
                        pos.manual_avg_price = 0.0

        if pos:
            pos.manual_quantity = max(0.0, pos.quantity - pos.auto_quantity)
            pos.cost_basis_krw = pos.auto_cost_basis_krw + pos.manual_cost_basis_krw
            self._recalc_avg(pos)
            if pos.quantity <= 1e-12:
                self.positions.pop(sym, None)
        return pnl

    def set_exit_plan(
        self,
        symbol: str,
        *,
        custom_sl_tp: bool,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        stop_loss_usdt: float | None = None,
        take_profit_usdt: float | None = None,
        config: AppConfig,
    ) -> Optional[Position]:
        sym = symbol.upper()
        pos = self.positions.get(sym)
        if not pos:
            return None
        entry = pos.avg_price or pos.auto_avg_price or pos.current_price
        pos.custom_sl_tp = custom_sl_tp
        sl_r = config.stop_loss_pct / 100
        tp_r = config.take_profit_pct / 100
        if custom_sl_tp:
            if stop_loss_pct is not None and stop_loss_pct > 0 and entry > 0:
                pos.custom_stop_loss_pct = float(stop_loss_pct)
                pos.stop_loss = entry * (1 - stop_loss_pct / 100)
            elif stop_loss_usdt is not None and stop_loss_usdt > 0:
                pos.stop_loss = stop_loss_usdt
                if entry > 0:
                    pos.custom_stop_loss_pct = max(
                        0.01, (entry - stop_loss_usdt) / entry * 100
                    )
            elif entry > 0:
                pos.custom_stop_loss_pct = config.stop_loss_pct
                pos.stop_loss = entry * (1 - sl_r)

            if take_profit_pct is not None and take_profit_pct > 0 and entry > 0:
                pos.custom_take_profit_pct = float(take_profit_pct)
                pos.take_profit = entry * (1 + take_profit_pct / 100)
            elif take_profit_usdt is not None and take_profit_usdt > 0:
                pos.take_profit = take_profit_usdt
                if entry > 0:
                    pos.custom_take_profit_pct = max(
                        0.01, (take_profit_usdt - entry) / entry * 100
                    )
            elif entry > 0:
                pos.custom_take_profit_pct = config.take_profit_pct
                pos.take_profit = entry * (1 + tp_r)
        else:
            pos.custom_stop_loss_pct = 0.0
            pos.custom_take_profit_pct = 0.0
            if entry > 0:
                pos.stop_loss = entry * (1 - sl_r)
                pos.take_profit = entry * (1 + tp_r)
        self._recalc_avg(pos)
        return pos

    def set_exclude(self, symbol: str, exclude: bool) -> Optional[Position]:
        pos = self.positions.get(symbol)
        if not pos:
            return None
        if exclude:
            if pos.auto_quantity > 0:
                pos.manual_quantity += pos.auto_quantity
                pos.manual_cost_basis_krw += pos.auto_cost_basis_krw
                if pos.manual_quantity > 0:
                    pos.manual_avg_price = (
                        pos.manual_cost_basis_krw / self.usdt_krw / pos.manual_quantity
                    )
                pos.auto_quantity = 0.0
                pos.auto_cost_basis_krw = 0.0
                pos.auto_avg_price = 0.0
            pos.excluded_from_auto = True
        else:
            pos.excluded_from_auto = False
        self._recalc_avg(pos)
        return pos

    def snapshot(
        self,
        prices: dict[str, float],
        config: AppConfig,
        *,
        upbit_truth: bool = False,
        upbit_synced_at: float | None = None,
    ) -> PortfolioSnapshot:
        invested = 0.0
        principal = 0.0
        unrealized = 0.0
        pos_list: list[Position] = []

        for sym, pos in self.positions.items():
            if upbit_truth and pos.current_price_krw > 0:
                px = pos.current_price_krw / max(self.usdt_krw, 1.0)
            else:
                px = prices.get(sym, pos.current_price or pos.avg_price)
            pos.current_price = px
            self._recalc_avg(pos)

            if upbit_truth and pos.exchange_quantity > 0:
                qty = pos.exchange_quantity
                if pos.quantity > qty:
                    qty = pos.quantity
                px_krw = pos.current_price_krw
                if sym in prices and prices[sym] > 0:
                    pos.current_price = prices[sym]
                    px_krw = prices[sym] * max(self.usdt_krw, 1.0)
                    pos.current_price_krw = px_krw
                cost_krw = (
                    pos.avg_buy_price_krw * qty
                    if pos.avg_buy_price_krw > 0
                    else pos.cost_basis_krw
                )
                if cost_krw <= 0 and pos.avg_price > 0:
                    cost_krw = self.usdt_to_krw(qty * pos.avg_price)
                val_krw = qty * px_krw if px_krw > 0 else pos.valuation_krw
                pos.valuation_krw = val_krw
                pnl_krw = val_krw - cost_krw
                pos.cost_basis_krw = round(cost_krw, 0)
                pos.current_value_krw = round(val_krw, 0)
                pos.pnl_krw = round(pnl_krw, 0)
                if pos.auto_quantity > 0:
                    aq = pos.auto_quantity / max(qty, 1e-12)
                    pos.auto_value_krw = round(val_krw * aq, 0)
                    ac = cost_krw * aq
                    pos.auto_pnl_krw = round(pos.auto_value_krw - ac, 0)
                if pos.manual_quantity > 0:
                    mq = pos.manual_quantity / max(qty, 1e-12)
                    pos.manual_value_krw = round(val_krw * mq, 0)
                    mc = cost_krw * mq
                    pos.manual_pnl_krw = round(pos.manual_value_krw - mc, 0)
                invested += val_krw
                principal += cost_krw
                unrealized += pnl_krw
                pos_list.append(pos)
                continue

            cost_krw = pos.cost_basis_krw
            if cost_krw <= 0 and pos.quantity > 0 and pos.avg_price > 0:
                cost_krw = self.usdt_to_krw(pos.quantity * pos.avg_price)
                pos.cost_basis_krw = cost_krw
                if pos.auto_quantity > 0 and pos.auto_cost_basis_krw <= 0:
                    pos.auto_cost_basis_krw = (
                        cost_krw * (pos.auto_quantity / pos.quantity)
                        if pos.manual_quantity > 0
                        else cost_krw
                    )
                if pos.manual_quantity > 0 and pos.manual_cost_basis_krw <= 0:
                    pos.manual_cost_basis_krw = cost_krw - pos.auto_cost_basis_krw
            # USDT 기준 손익 후 원화 환산 (매수·평가 환율 불일치로 가짜 수익 방지)
            cost_usdt = pos.quantity * pos.avg_price
            current_usdt = pos.quantity * px
            pnl_usdt = current_usdt - cost_usdt
            pnl_krw = self.usdt_to_krw(pnl_usdt)
            val_krw = cost_krw + pnl_krw
            auto_cost_usdt = pos.auto_quantity * pos.auto_avg_price
            auto_current_usdt = pos.auto_quantity * px
            auto_pnl_usdt = auto_current_usdt - auto_cost_usdt
            manual_cost_usdt = pos.manual_quantity * pos.manual_avg_price
            manual_pnl_usdt = (pos.manual_quantity * px) - manual_cost_usdt
            pos.current_value_krw = round(val_krw, 0)
            pos.auto_value_krw = round(
                pos.auto_cost_basis_krw + self.usdt_to_krw(auto_pnl_usdt), 0
            )
            pos.manual_value_krw = round(
                pos.manual_cost_basis_krw + self.usdt_to_krw(manual_pnl_usdt), 0
            )
            pos.pnl_krw = round(pnl_krw, 0)
            pos.auto_pnl_krw = round(self.usdt_to_krw(auto_pnl_usdt), 0) if pos.auto_quantity > 0 else 0.0
            pos.manual_pnl_krw = (
                round(self.usdt_to_krw(manual_pnl_usdt), 0) if pos.manual_quantity > 0 else 0.0
            )
            invested += val_krw
            principal += cost_krw
            unrealized += pnl_krw
            pos_list.append(pos)

        total = self.cash_krw + invested
        for pos in pos_list:
            pos.weight_pct = round(
                (pos.current_value_krw / total * 100) if total > 0 else 0, 1
            )

        profit_toward = self.realized_pnl_krw + unrealized
        progress = (
            min(100.0, max(0.0, profit_toward / config.target_profit_krw * 100))
            if config.target_profit_krw > 0
            else 0.0
        )

        return PortfolioSnapshot(
            cash_krw=round(self.cash_krw, 0),
            total_value_krw=round(total, 0),
            invested_krw=round(invested, 0),
            principal_krw=round(principal, 0),
            unrealized_pnl_krw=round(unrealized, 0),
            realized_pnl_krw=round(self.realized_pnl_krw, 0),
            profit_toward_target_krw=round(profit_toward, 0),
            target_profit_krw=config.target_profit_krw,
            progress_pct=round(progress, 1),
            positions=sorted(pos_list, key=lambda p: p.current_value_krw, reverse=True),
            data_source="upbit" if upbit_truth else "paper",
            upbit_synced_at=upbit_synced_at,
        )

    def buy(
        self,
        symbol: str,
        base: str,
        price_usdt: float,
        allocation_krw: float,
        stop_loss_pct: float,
        take_profit_pct: float,
        score: float = 0.0,
        reason: str = "AI 매수",
        entry_reason: str = "",
        entry_score: float = 0.0,
        entry_outlook: str = "",
        auto_managed: bool = True,
        min_buy_krw: float | None = None,
    ) -> Optional[Position]:
        from app.engine.buy_limits import effective_min_buy_krw

        floor = (
            max(1.0, float(min_buy_krw))
            if min_buy_krw is not None
            else effective_min_buy_krw()
        )
        fee_rate = getattr(self, "trading_fee_pct", 0.05) / 100
        max_spend = self.cash_krw / (1 + fee_rate) if fee_rate > 0 else self.cash_krw
        cost_krw = min(allocation_krw, max_spend)
        if cost_krw < floor:
            return None
        fee_krw = self._fee_krw(cost_krw)
        usdt = self.krw_to_usdt(cost_krw)
        qty = usdt / price_usdt
        if qty <= 0:
            return None
        # 매수 시점 환율로 수량·원금을 맞춤 (이후 평가는 USDT 손익 × 현재 환율)
        fx_at_buy = self.usdt_krw
        meta = coin_meta(symbol, base)
        self.cash_krw -= cost_krw + fee_krw
        self.realized_pnl_krw -= fee_krw

        if symbol in self.positions:
            pos = self.positions[symbol]
            if auto_managed:
                new_auto = pos.auto_quantity + qty
                pos.auto_cost_basis_krw += cost_krw
                pos.auto_avg_price = (
                    pos.auto_cost_basis_krw / fx_at_buy / new_auto if new_auto else price_usdt
                )
                pos.auto_quantity = new_auto
                pos.excluded_from_auto = False
                if pos.stop_loss <= 0:
                    pos.stop_loss = price_usdt * (1 - stop_loss_pct)
                    pos.take_profit = price_usdt * (1 + take_profit_pct)
                pos.auto_exit_sl_pct = round(stop_loss_pct * 100, 4)
                pos.auto_exit_tp_pct = round(take_profit_pct * 100, 4)
                pos.trailing_high = max(pos.trailing_high, price_usdt)
            else:
                new_man = pos.manual_quantity + qty
                pos.manual_cost_basis_krw += cost_krw
                pos.manual_avg_price = (
                    pos.manual_cost_basis_krw / fx_at_buy / new_man if new_man else price_usdt
                )
                pos.manual_quantity = new_man
            pos.cost_basis_krw += cost_krw
            pos.current_price = price_usdt
            self._recalc_avg(pos)
            self.trades.append(
                self._trade_event(meta, symbol, "BUY", price_usdt, qty, reason, auto_managed)
            )
            return pos

        pos = Position(
            symbol=symbol,
            base=meta["base"],
            name_ko=meta["name_ko"],
            name_en=meta["name_en"],
            pair_label=meta["pair_label"],
            display=meta["display"],
            auto_quantity=qty if auto_managed else 0.0,
            manual_quantity=0.0 if auto_managed else qty,
            avg_price=price_usdt,
            auto_avg_price=price_usdt if auto_managed else 0.0,
            manual_avg_price=0.0 if auto_managed else price_usdt,
            current_price=price_usdt,
            stop_loss=price_usdt * (1 - stop_loss_pct) if auto_managed else 0.0,
            take_profit=price_usdt * (1 + take_profit_pct) if auto_managed else 0.0,
            trailing_high=price_usdt if auto_managed else 0.0,
            opened_at=time.time(),
            score=score,
            cost_basis_krw=cost_krw,
            auto_cost_basis_krw=cost_krw if auto_managed else 0.0,
            manual_cost_basis_krw=0.0 if auto_managed else cost_krw,
            entry_reason=entry_reason,
            entry_score=entry_score,
            entry_outlook=entry_outlook or ("AI 자동투자" if auto_managed else ""),
            auto_exit_sl_pct=round(stop_loss_pct * 100, 4) if auto_managed else 0.0,
            auto_exit_tp_pct=round(take_profit_pct * 100, 4) if auto_managed else 0.0,
            excluded_from_auto=False,
        )
        if not auto_managed:
            pos.manual_quantity = qty
        self.positions[symbol] = pos
        self.trades.append(
            self._trade_event(meta, symbol, "BUY", price_usdt, qty, reason, auto_managed)
        )
        return pos

    def sell(
        self,
        symbol: str,
        price_usdt: float,
        reason: str,
        percent: float = 100.0,
        from_auto_only: bool = False,
        auto_only: bool = False,
    ) -> Optional[TradeEvent]:
        """auto_only=True: AI 익절/손절 — auto_quantity 만 매도."""
        pos = self.positions.get(symbol)
        if not pos:
            return None

        pct = min(100.0, max(1.0, percent)) / 100.0
        meta = coin_meta(symbol, pos.base)

        if auto_only or from_auto_only:
            base_qty = pos.auto_quantity
            if base_qty <= 0:
                return None
            sell_qty = base_qty if pct >= 0.999 else base_qty * pct
            cost_portion = pos.auto_cost_basis_krw * (sell_qty / base_qty)
            avg_px = pos.auto_avg_price if pos.auto_avg_price > 0 else price_usdt
            proceeds_krw, pnl_delta = self._sell_cash_flow(
                sell_qty, price_usdt, avg_px, cost_portion
            )
            self.realized_pnl_krw += pnl_delta
            self.cash_krw += proceeds_krw
            pos.auto_quantity -= sell_qty
            pos.auto_cost_basis_krw -= cost_portion
            pos.cost_basis_krw -= cost_portion
            if pos.auto_quantity <= 1e-12:
                pos.auto_quantity = 0.0
                pos.auto_cost_basis_krw = 0.0
                pos.auto_avg_price = 0.0
            is_auto = True
            self._recalc_avg(pos)
        else:
            sell_qty = pos.quantity * pct
            if sell_qty <= 0:
                return None
            cost_portion = pos.cost_basis_krw * (sell_qty / pos.quantity)
            auto_part = min(sell_qty, pos.auto_quantity)
            man_part = sell_qty - auto_part
            if auto_part > 0 and pos.auto_quantity > 0:
                cost_a = pos.auto_cost_basis_krw * (auto_part / pos.auto_quantity)
                pos.auto_quantity -= auto_part
                pos.auto_cost_basis_krw = max(0, pos.auto_cost_basis_krw - cost_a)
            if man_part > 0 and pos.manual_quantity > 0:
                cost_m = pos.manual_cost_basis_krw * (man_part / pos.manual_quantity)
                pos.manual_quantity -= man_part
                pos.manual_cost_basis_krw = max(0, pos.manual_cost_basis_krw - cost_m)
            avg_px = pos.avg_price if pos.avg_price > 0 else price_usdt
            proceeds_krw, pnl_delta = self._sell_cash_flow(
                sell_qty, price_usdt, avg_px, cost_portion
            )
            self.realized_pnl_krw += pnl_delta
            self.cash_krw += proceeds_krw
            pos.cost_basis_krw -= cost_portion
            is_auto = False
            self._recalc_avg(pos)

        evt = self._trade_event(meta, symbol, "SELL", price_usdt, sell_qty, reason, is_auto)
        self.trades.append(evt)

        if pos.quantity <= 1e-12:
            self.positions.pop(symbol, None)
        return evt

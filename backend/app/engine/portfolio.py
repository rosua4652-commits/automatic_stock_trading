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

    def apply_config(self, config: AppConfig) -> None:
        if not self.positions and not self.trades:
            self.cash_krw = config.initial_balance_krw
            self.realized_pnl_krw = 0.0

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
    ) -> TradeEvent:
        amount_usdt = price * quantity
        return TradeEvent(
            ts=time.time(),
            symbol=symbol,
            base=meta["base"],
            display=meta["display"],
            side=side,
            price=price,
            quantity=quantity,
            amount_krw=round(self.usdt_to_krw(amount_usdt), 0),
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

    def snapshot(self, prices: dict[str, float], config: AppConfig) -> PortfolioSnapshot:
        invested = 0.0
        principal = 0.0
        unrealized = 0.0
        pos_list: list[Position] = []

        for sym, pos in self.positions.items():
            px = prices.get(sym, pos.current_price or pos.avg_price)
            pos.current_price = px
            self._recalc_avg(pos)
            val_krw = self.usdt_to_krw(pos.value_usdt)
            cost_krw = pos.cost_basis_krw
            pnl_krw = val_krw - cost_krw
            auto_val = self.usdt_to_krw(pos.auto_value_usdt)
            manual_val = val_krw - auto_val
            pos.current_value_krw = round(val_krw, 0)
            pos.auto_value_krw = round(auto_val, 0)
            pos.manual_value_krw = round(manual_val, 0)
            pos.pnl_krw = round(pnl_krw, 0)
            if pos.auto_quantity > 0 and pos.auto_avg_price > 0:
                pos.auto_pnl_krw = round(
                    self.usdt_to_krw(
                        (px - pos.auto_avg_price) * pos.auto_quantity
                    ),
                    0,
                )
            else:
                pos.auto_pnl_krw = 0.0
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
    ) -> Optional[Position]:
        cost_krw = min(allocation_krw, self.cash_krw * 0.95)
        if cost_krw < 50_000:
            return None
        usdt = self.krw_to_usdt(cost_krw)
        qty = usdt / price_usdt
        if qty <= 0:
            return None
        meta = coin_meta(symbol, base)
        self.cash_krw -= cost_krw

        if symbol in self.positions:
            pos = self.positions[symbol]
            if auto_managed:
                new_auto = pos.auto_quantity + qty
                pos.auto_cost_basis_krw += cost_krw
                pos.auto_avg_price = (
                    pos.auto_cost_basis_krw / self.usdt_krw / new_auto if new_auto else price_usdt
                )
                pos.auto_quantity = new_auto
                if pos.stop_loss <= 0:
                    pos.stop_loss = price_usdt * (1 - stop_loss_pct)
                    pos.take_profit = price_usdt * (1 + take_profit_pct)
                pos.trailing_high = max(pos.trailing_high, price_usdt)
            else:
                new_man = pos.manual_quantity + qty
                pos.manual_cost_basis_krw += cost_krw
                pos.manual_avg_price = (
                    pos.manual_cost_basis_krw / self.usdt_krw / new_man if new_man else price_usdt
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
            entry_outlook=entry_outlook,
            excluded_from_auto=not auto_managed,
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
            proceeds_krw = self.usdt_to_krw(sell_qty * price_usdt)
            self.realized_pnl_krw += proceeds_krw - cost_portion
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
            proceeds_krw = self.usdt_to_krw(sell_qty * price_usdt)
            self.realized_pnl_krw += proceeds_krw - cost_portion
            self.cash_krw += proceeds_krw
            pos.cost_basis_krw -= cost_portion
            is_auto = False
            self._recalc_avg(pos)

        evt = self._trade_event(meta, symbol, "SELL", price_usdt, sell_qty, reason, is_auto)
        self.trades.append(evt)

        if pos.quantity <= 1e-12:
            self.positions.pop(symbol, None)
        return evt

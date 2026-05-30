import time
from typing import Optional

from app.config import settings
from app.market.coin_registry import coin_meta
from app.models import AppConfig, PortfolioSnapshot, Position, TradeEvent


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

    def _trade_event(
        self,
        pos_meta: dict,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        reason: str,
    ) -> TradeEvent:
        amount_usdt = price * quantity
        amount_krw = self.usdt_to_krw(amount_usdt)
        return TradeEvent(
            ts=time.time(),
            symbol=symbol,
            base=pos_meta["base"],
            display=pos_meta["display"],
            side=side,
            price=price,
            quantity=quantity,
            amount_krw=round(amount_krw, 0),
            amount_usdt=round(amount_usdt, 4),
            reason=reason,
        )

    def snapshot(self, prices: dict[str, float], config: AppConfig) -> PortfolioSnapshot:
        invested = 0.0
        principal = 0.0
        unrealized = 0.0
        pos_list: list[Position] = []

        for sym, pos in self.positions.items():
            px = prices.get(sym, pos.current_price or pos.avg_price)
            pos.current_price = px
            val_krw = self.usdt_to_krw(pos.value_usdt)
            cost_krw = pos.cost_basis_krw
            pnl_krw = val_krw - cost_krw
            pos.current_value_krw = round(val_krw, 0)
            pos.pnl_krw = round(pnl_krw, 0)
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
            old = self.positions[symbol]
            new_qty = old.quantity + qty
            new_cost = old.cost_basis_krw + cost_krw
            new_avg = (old.avg_price * old.quantity + price_usdt * qty) / new_qty
            old.quantity = new_qty
            old.avg_price = new_avg
            old.cost_basis_krw = new_cost
            old.current_price = price_usdt
            old.trailing_high = max(old.trailing_high, price_usdt)
            self.trades.append(
                self._trade_event(meta, symbol, "BUY", price_usdt, qty, reason)
            )
            return old

        pos = Position(
            symbol=symbol,
            base=meta["base"],
            name_ko=meta["name_ko"],
            name_en=meta["name_en"],
            pair_label=meta["pair_label"],
            display=meta["display"],
            quantity=qty,
            avg_price=price_usdt,
            current_price=price_usdt,
            stop_loss=price_usdt * (1 - stop_loss_pct),
            take_profit=price_usdt * (1 + take_profit_pct),
            trailing_high=price_usdt,
            opened_at=time.time(),
            score=score,
            cost_basis_krw=cost_krw,
            entry_reason=entry_reason,
            entry_score=entry_score,
            entry_outlook=entry_outlook,
            auto_managed=auto_managed,
        )
        self.positions[symbol] = pos
        self.trades.append(
            self._trade_event(meta, symbol, "BUY", price_usdt, qty, reason)
        )
        return pos

    def sell(
        self,
        symbol: str,
        price_usdt: float,
        reason: str,
        percent: float = 100.0,
    ) -> Optional[TradeEvent]:
        pos = self.positions.get(symbol)
        if not pos:
            return None

        pct = min(100.0, max(1.0, percent))
        sell_qty = pos.quantity if pct >= 99.9 else pos.quantity * (pct / 100.0)
        if sell_qty <= 0:
            return None

        meta = coin_meta(symbol, pos.base)
        proceeds_krw = self.usdt_to_krw(sell_qty * price_usdt)
        cost_portion = pos.cost_basis_krw * (sell_qty / pos.quantity)
        self.realized_pnl_krw += proceeds_krw - cost_portion
        self.cash_krw += proceeds_krw

        evt = self._trade_event(meta, symbol, "SELL", price_usdt, sell_qty, reason)

        if pct >= 99.9:
            self.positions.pop(symbol, None)
        else:
            pos.quantity -= sell_qty
            pos.cost_basis_krw -= cost_portion
            if pos.quantity <= 1e-12:
                self.positions.pop(symbol, None)

        self.trades.append(evt)
        return evt

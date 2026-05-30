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

    def set_fx(self, rate: float) -> None:
        self.usdt_krw = rate

    def usdt_to_krw(self, usdt: float) -> float:
        return usdt * self.usdt_krw

    def krw_to_usdt(self, krw: float) -> float:
        return krw / self.usdt_krw

    def snapshot(self, prices: dict[str, float], config: AppConfig) -> PortfolioSnapshot:
        invested = 0.0
        unrealized = 0.0
        pos_list: list[Position] = []

        for sym, pos in self.positions.items():
            px = prices.get(sym, pos.current_price or pos.avg_price)
            pos.current_price = px
            invested += self.usdt_to_krw(pos.value)
            unrealized += self.usdt_to_krw(pos.pnl)
            pos_list.append(pos)

        total = self.cash_krw + invested
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
            unrealized_pnl_krw=round(unrealized, 0),
            realized_pnl_krw=round(self.realized_pnl_krw, 0),
            profit_toward_target_krw=round(profit_toward, 0),
            target_profit_krw=config.target_profit_krw,
            progress_pct=round(progress, 1),
            positions=sorted(pos_list, key=lambda p: p.value, reverse=True),
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
        )
        self.positions[symbol] = pos
        self.trades.append(
            TradeEvent(
                ts=time.time(),
                symbol=symbol,
                base=meta["base"],
                display=meta["display"],
                side="BUY",
                price=price_usdt,
                quantity=qty,
                reason="AI 매수",
            )
        )
        return pos

    def sell(self, symbol: str, price_usdt: float, reason: str) -> Optional[TradeEvent]:
        pos = self.positions.pop(symbol, None)
        if not pos:
            return None
        proceeds_krw = self.usdt_to_krw(pos.quantity * price_usdt)
        cost_krw = self.usdt_to_krw(pos.quantity * pos.avg_price)
        self.realized_pnl_krw += proceeds_krw - cost_krw
        self.cash_krw += proceeds_krw
        evt = TradeEvent(
            ts=time.time(),
            symbol=symbol,
            base=pos.base,
            display=pos.display,
            side="SELL",
            price=price_usdt,
            quantity=pos.quantity,
            reason=reason,
        )
        self.trades.append(evt)
        return evt

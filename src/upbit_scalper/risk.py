from __future__ import annotations

from dataclasses import dataclass

from .config import RiskSettings


@dataclass(frozen=True)
class PositionPlan:
    market: str
    entry_price: float
    budget_krw: float
    take_profit_price: float
    stop_loss_price: float
    trailing_stop_pct: float
    expected_gross_profit_pct: float
    expected_net_profit_pct: float


@dataclass
class RiskState:
    realized_pnl_krw: float = 0.0
    open_positions: int = 0
    consecutive_losses: int = 0


class RiskManager:
    def __init__(self, settings: RiskSettings, state: RiskState | None = None) -> None:
        self.settings = settings
        self.state = state or RiskState()

    def can_open_new_position(self) -> tuple[bool, str]:
        if self.state.open_positions >= self.settings.max_open_positions:
            return False, "max open positions reached"
        if self.state.realized_pnl_krw <= -abs(self.settings.daily_loss_limit_krw):
            return False, "daily loss limit reached"
        if self.state.consecutive_losses >= self.settings.stop_after_consecutive_losses:
            return False, "consecutive loss stop reached"
        return True, "ok"

    def plan_position(self, market: str, entry_price: float, score: float) -> PositionPlan:
        budget = min(self.settings.max_position_krw, self.settings.total_budget_krw)
        if score < 90:
            budget *= 0.75
        budget = max(self.settings.min_position_krw, budget)
        budget = min(budget, self.settings.total_budget_krw)

        take_profit_price = entry_price * (1 + self.settings.take_profit_pct / 100)
        stop_loss_price = entry_price * (1 - self.settings.stop_loss_pct / 100)
        expected_net = self.settings.take_profit_pct - self.settings.round_trip_cost_pct
        return PositionPlan(
            market=market,
            entry_price=entry_price,
            budget_krw=budget,
            take_profit_price=take_profit_price,
            stop_loss_price=stop_loss_price,
            trailing_stop_pct=self.settings.trailing_stop_pct,
            expected_gross_profit_pct=self.settings.take_profit_pct,
            expected_net_profit_pct=expected_net,
        )

    def validate_plan(self, plan: PositionPlan) -> tuple[bool, str]:
        ok, reason = self.can_open_new_position()
        if not ok:
            return ok, reason
        if plan.expected_net_profit_pct < self.settings.min_expected_net_profit_pct:
            return False, "expected net profit is below minimum threshold"
        if plan.budget_krw > self.settings.max_position_krw:
            return False, "position budget exceeds max position"
        if plan.budget_krw > self.settings.total_budget_krw:
            return False, "position budget exceeds total budget"
        return True, "ok"

    def record_closed_trade(self, pnl_krw: float) -> None:
        self.state.realized_pnl_krw += pnl_krw
        if pnl_krw < 0:
            self.state.consecutive_losses += 1
        else:
            self.state.consecutive_losses = 0

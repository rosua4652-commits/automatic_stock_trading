from __future__ import annotations

from dataclasses import dataclass

from .config import RiskSettings
from .risk import PositionPlan
from .upbit import Candle


@dataclass(frozen=True)
class SimulatedTrade:
    market: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    budget_krw: float
    pnl_krw: float
    pnl_pct: float
    reason: str


@dataclass(frozen=True)
class SimulationResult:
    trades: list[SimulatedTrade]
    total_pnl_krw: float
    win_rate_pct: float
    max_drawdown_krw: float


class PaperBroker:
    def __init__(self, settings: RiskSettings) -> None:
        self.settings = settings

    def simulate_position(self, plan: PositionPlan, future_candles: list[Candle]) -> SimulatedTrade | None:
        if not future_candles:
            return None

        highest = plan.entry_price
        exit_price = future_candles[-1].trade_price
        exit_time = future_candles[-1].timestamp
        reason = "end_of_window"

        for candle in future_candles:
            highest = max(highest, candle.high_price)
            trailing_stop_price = highest * (1 - plan.trailing_stop_pct / 100)

            if candle.low_price <= plan.stop_loss_price:
                exit_price = plan.stop_loss_price
                exit_time = candle.timestamp
                reason = "stop_loss"
                break
            if candle.high_price >= plan.take_profit_price:
                exit_price = plan.take_profit_price
                exit_time = candle.timestamp
                reason = "take_profit"
                break
            if candle.low_price <= trailing_stop_price and highest > plan.entry_price:
                exit_price = trailing_stop_price
                exit_time = candle.timestamp
                reason = "trailing_stop"
                break

        gross_pct = ((exit_price - plan.entry_price) / plan.entry_price) * 100
        net_pct = gross_pct - self.settings.round_trip_cost_pct
        pnl = plan.budget_krw * (net_pct / 100)
        return SimulatedTrade(
            market=plan.market,
            entry_time=future_candles[0].timestamp,
            exit_time=exit_time,
            entry_price=plan.entry_price,
            exit_price=exit_price,
            budget_krw=plan.budget_krw,
            pnl_krw=pnl,
            pnl_pct=net_pct,
            reason=reason,
        )


def summarize_trades(trades: list[SimulatedTrade]) -> SimulationResult:
    total = sum(trade.pnl_krw for trade in trades)
    wins = sum(1 for trade in trades if trade.pnl_krw > 0)
    win_rate = (wins / len(trades) * 100) if trades else 0.0

    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for trade in trades:
        equity += trade.pnl_krw
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)

    return SimulationResult(
        trades=trades,
        total_pnl_krw=total,
        win_rate_pct=win_rate,
        max_drawdown_krw=max_drawdown,
    )

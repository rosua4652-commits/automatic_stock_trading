from __future__ import annotations

from dataclasses import dataclass, field

from .config import RiskSettings
from .indicators import IndicatorSnapshot, percent_change, snapshot
from .risk import PositionPlan, RiskManager
from .upbit import Candle


@dataclass(frozen=True)
class MarketContext:
    btc_5m_change_pct: float
    market_breadth_pct: float | None = None
    theme_note: str = ""

    def is_risk_off(self, settings: RiskSettings) -> bool:
        return self.btc_5m_change_pct <= settings.btc_crash_5m_pct


@dataclass(frozen=True)
class Signal:
    market: str
    score: float
    strategy: str
    action: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    indicators: IndicatorSnapshot | None = None
    plan: PositionPlan | None = None

    @property
    def should_enter(self) -> bool:
        return self.action == "enter"


class ScalpingStrategy:
    """Rule-based scalping engine for volume breakout and pullback entries."""

    def __init__(self, risk_settings: RiskSettings) -> None:
        self.risk_settings = risk_settings

    def evaluate(self, market: str, candles_5m: list[Candle], context: MarketContext) -> Signal:
        if len(candles_5m) < 80:
            return Signal(market, 0, "insufficient_data", "watch", warnings=["Need at least 80 candles"])

        indicators = snapshot(candles_5m)
        recent_change = percent_change(candles_5m[-7].trade_price, candles_5m[-1].trade_price)
        prior_high = max(candle.high_price for candle in candles_5m[-21:-1])
        latest = candles_5m[-1]

        score = 0.0
        reasons: list[str] = []
        warnings: list[str] = []
        strategy = "watch"

        if context.is_risk_off(self.risk_settings):
            warnings.append(f"BTC 5m change {context.btc_5m_change_pct:.2f}% is risk-off")
            return Signal(market, 0, "market_risk_off", "watch", reasons, warnings, indicators)

        if indicators.volume_ratio20 and indicators.volume_ratio20 >= 2.5:
            score += 22
            reasons.append(f"volume ratio {indicators.volume_ratio20:.2f}x")
        elif indicators.volume_ratio20 and indicators.volume_ratio20 >= 1.5:
            score += 12
            reasons.append(f"volume ratio {indicators.volume_ratio20:.2f}x")
        else:
            warnings.append("volume expansion is weak")

        if indicators.ema5 and indicators.ema20 and indicators.ema60:
            if indicators.ema5 > indicators.ema20 > indicators.ema60:
                score += 18
                reasons.append("EMA 5/20/60 bullish alignment")
            elif indicators.ema5 > indicators.ema20:
                score += 10
                reasons.append("short-term EMA bullish")

        if indicators.vwap20 and indicators.close > indicators.vwap20:
            score += 10
            reasons.append("price is above VWAP20")

        if indicators.macd is not None and indicators.macd_signal is not None and indicators.macd > indicators.macd_signal:
            score += 12
            reasons.append("MACD is above signal")

        if indicators.rsi14 is not None:
            if 50 <= indicators.rsi14 <= 72:
                score += 15
                reasons.append(f"RSI {indicators.rsi14:.1f} is momentum-friendly")
            elif 35 <= indicators.rsi14 < 50:
                score += 8
                reasons.append(f"RSI {indicators.rsi14:.1f} is recovering")
            elif indicators.rsi14 > 78:
                score -= 18
                warnings.append(f"RSI {indicators.rsi14:.1f} is overheated")

        is_breakout = latest.trade_price > prior_high
        if is_breakout:
            score += 18
            strategy = "volume_breakout"
            reasons.append("latest close broke prior 20-candle high")

        if self._is_pullback_rebound(candles_5m, indicators):
            score += 16
            strategy = "pullback_rebound"
            reasons.append("pullback near short EMA is rebounding")

        if indicators.bb_upper and latest.trade_price > indicators.bb_upper and indicators.rsi14 and indicators.rsi14 > 75:
            score -= 12
            warnings.append("Bollinger upper break with high RSI can be chase-risk")

        if recent_change > 8:
            score -= 20
            warnings.append(f"recent 30m change {recent_change:.2f}% is too extended")
        elif recent_change > 3:
            score += 6
            reasons.append(f"recent 30m momentum {recent_change:.2f}%")

        score = max(0.0, min(100.0, score))
        action = "enter" if score >= 80 and not warnings_block_entry(warnings) else "watch"
        if strategy == "watch" and action == "enter":
            strategy = "momentum_scalp"

        risk_manager = RiskManager(self.risk_settings)
        plan = risk_manager.plan_position(market, latest.trade_price, score) if action == "enter" else None
        if plan:
            valid, reason = risk_manager.validate_plan(plan)
            if not valid:
                action = "watch"
                warnings.append(reason)
                plan = None

        return Signal(market, score, strategy, action, reasons, warnings, indicators, plan)

    def _is_pullback_rebound(self, candles: list[Candle], indicators: IndicatorSnapshot) -> bool:
        if not indicators.ema5 or not indicators.ema20 or not indicators.rsi14:
            return False
        latest = candles[-1]
        previous = candles[-2]
        bullish_candle = latest.trade_price > latest.opening_price and latest.trade_price > previous.trade_price
        near_ema = latest.low_price <= indicators.ema20 * 1.004 and latest.trade_price > indicators.ema5
        rsi_recovered = 42 <= indicators.rsi14 <= 68
        return bullish_candle and near_ema and rsi_recovered


def warnings_block_entry(warnings: list[str]) -> bool:
    blocking_keywords = ("risk-off", "overheated", "too extended")
    return any(any(keyword in warning for keyword in blocking_keywords) for warning in warnings)

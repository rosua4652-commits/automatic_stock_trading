"""자동투자 청산 강도 — 약(weak) / 중(medium) / 강(strong)."""

from __future__ import annotations

from dataclasses import dataclass

from app.models import AppConfig
from app.util.numbers import as_float

STRENGTH_WEAK = "weak"
STRENGTH_MEDIUM = "medium"
STRENGTH_STRONG = "strong"

_STRENGTH_ALIASES = {
    "weak": STRENGTH_WEAK,
    "약": STRENGTH_WEAK,
    "medium": STRENGTH_MEDIUM,
    "중": STRENGTH_MEDIUM,
    "strong": STRENGTH_STRONG,
    "강": STRENGTH_STRONG,
}


@dataclass(frozen=True)
class ExitStrengthProfile:
    key: str
    label_ko: str
    base_sl_pct: float
    base_tp_pct: float
    trailing_enabled: bool
    trailing_activate_pct: float
    trailing_distance_pct: float
    adaptive_tp: bool
    tp_pullback_pct: float


def normalize_exit_strength(value: str | None) -> str:
    if value is None:
        raw = STRENGTH_WEAK
    elif hasattr(value, "value"):
        raw = str(getattr(value, "value", value)).strip().lower()
    else:
        raw = str(value).strip().lower()
    return _STRENGTH_ALIASES.get(raw, STRENGTH_WEAK)


def get_exit_strength_profile(config: AppConfig | None) -> ExitStrengthProfile:
    key = normalize_exit_strength(
        getattr(config, "auto_exit_strength", None) if config else None
    )
    if key == STRENGTH_MEDIUM:
        return ExitStrengthProfile(
            key=key,
            label_ko="중",
            base_sl_pct=4.5,
            base_tp_pct=3.0,
            trailing_enabled=True,
            trailing_activate_pct=0.015,
            trailing_distance_pct=0.01,
            adaptive_tp=True,
            tp_pullback_pct=0.008,
        )
    if key == STRENGTH_STRONG:
        return ExitStrengthProfile(
            key=key,
            label_ko="강",
            base_sl_pct=7.0,
            base_tp_pct=6.0,
            trailing_enabled=True,
            trailing_activate_pct=0.025,
            trailing_distance_pct=0.018,
            adaptive_tp=True,
            tp_pullback_pct=0.012,
        )
    return ExitStrengthProfile(
        key=STRENGTH_WEAK,
        label_ko="약",
        base_sl_pct=2.5,
        base_tp_pct=1.2,
        trailing_enabled=False,
        trailing_activate_pct=0.05,
        trailing_distance_pct=0.03,
        adaptive_tp=False,
        tp_pullback_pct=0.0,
    )


def strength_default_sl_tp(config: AppConfig | None) -> tuple[float, float]:
    profile = get_exit_strength_profile(config)
    return profile.base_sl_pct, profile.base_tp_pct


def apply_strength_to_sl_tp(
    config: AppConfig | None,
    sl_pct: float,
    tp_pct: float,
    *,
    mode: str = "long",
) -> tuple[float, float]:
    """BT·학습 결과를 청산 강도 기준선에 맞춤 (급등 제외)."""
    if mode == "moonshot":
        return round(as_float(sl_pct, 6.0), 2), round(as_float(tp_pct, 20.0), 2)

    if mode == "scalp":
        tp = min(as_float(tp_pct, 4.0), 7.0)
        tp = max(tp, 2.5)
        sl = min(max(as_float(sl_pct, 3.5), 2.5), 5.5)
        sl = max(sl, tp * 1.25)
        return round(sl, 2), round(tp, 2)

    profile = get_exit_strength_profile(config)
    sl = as_float(sl_pct, profile.base_sl_pct)
    tp = as_float(tp_pct, profile.base_tp_pct)

    if profile.key == STRENGTH_WEAK:
        tp = min(max(tp, profile.base_tp_pct * 0.9), 2.5)
        sl = min(max(sl, 2.0), 4.0)
        sl = max(sl, tp * 1.35)
    elif profile.key == STRENGTH_MEDIUM:
        tp = min(max(tp, profile.base_tp_pct * 0.85), 5.0)
        sl = min(max(sl, 3.5), 6.5)
        sl = max(sl, tp * 1.15)
    else:
        tp = min(max(tp, profile.base_tp_pct * 0.85), 10.0)
        sl = min(max(sl, 5.5), 10.0)
        sl = max(sl, tp * 1.1)
    return round(sl, 2), round(tp, 2)


def apply_adaptive_exit_levels(
    pos,
    entry: float,
    price: float,
    config: AppConfig | None,
) -> None:
    """중·강: 고점 추적 손절 + 익절선 상향 조율."""
    profile = get_exit_strength_profile(config)
    if not profile.trailing_enabled or entry <= 0 or price <= 0:
        return

    auto_pnl = (price - entry) / entry
    if auto_pnl < profile.trailing_activate_pct:
        return

    if pos.trailing_high <= 0:
        pos.trailing_high = price
    if price > pos.trailing_high:
        pos.trailing_high = price

    trail_stop = pos.trailing_high * (1 - profile.trailing_distance_pct)
    if pos.stop_loss > 0:
        pos.stop_loss = max(pos.stop_loss, trail_stop)

    if profile.adaptive_tp and pos.trailing_high > 0:
        ratchet_tp = pos.trailing_high * (1 - profile.tp_pullback_pct)
        if pos.take_profit > 0:
            pos.take_profit = max(pos.take_profit, ratchet_tp)
        else:
            pos.take_profit = ratchet_tp

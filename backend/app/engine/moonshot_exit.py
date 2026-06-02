"""급등(moonshot) 전용 손익절 — 약·중·강(auto_exit_strength)과 완전 분리."""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.surge_classifier import is_moonshot_outlook, moonshot_sl_tp
from app.models import AppConfig
from app.util.numbers import as_float

MOMENTUM_WEAK = "weak"
MOMENTUM_MEDIUM = "medium"
MOMENTUM_STRONG = "strong"

EXIT_PROFILE_MOONSHOT = "moonshot"


@dataclass(frozen=True)
class MoonshotExitProfile:
    momentum_key: str
    label_ko: str
    base_sl_pct: float
    base_tp_pct: float
    trailing_activate_pct: float = 0.025
    trailing_distance_pct: float = 0.018
    tp_pullback_pct: float = 0.012


def _cfg_float(config: AppConfig | None, name: str, default: float) -> float:
    if config is None:
        return default
    return float(getattr(config, name, default) or default)


def is_moonshot_position(pos) -> bool:
    if pos is None:
        return False
    if str(getattr(pos, "exit_profile", "") or "").lower() == EXIT_PROFILE_MOONSHOT:
        return True
    outlook = str(getattr(pos, "entry_outlook", "") or "")
    # 단타 포지션은 사유에 '급등'이 있어도 moonshot 청산 경로 사용 안 함
    if "단타" in outlook:
        return False
    hint = f"{outlook} {getattr(pos, 'entry_reason', '')}"
    return is_moonshot_outlook(hint)


def is_moonshot_recommendation(rec) -> bool:
    tier = (getattr(rec, "entry_tier", "") or "").lower()
    if tier == "moonshot":
        return True
    # 단타 tier는 news_surge·급등 태그와 무관하게 moonshot TP/청산 제외
    if tier == "scalp":
        return False
    if bool(getattr(rec, "news_surge", False)):
        return True
    outlook = str(getattr(rec, "entry_detail", "") or "")
    return is_moonshot_outlook(outlook)


def _momentum_tier(change_24h: float, news_score: float) -> tuple[str, float, float]:
    """
    24h 상승률이 클수록 추격 진입 가능성 ↑ → 익절은 보수적으로 (늦은 진입).
    초기 급등(8~15%) 구간은 상대적으로 넓은 TP.
    """
    chg = float(change_24h or 0.0)
    if chg >= 40.0:
        tier, sl, tp = MOMENTUM_STRONG, 7.0, 8.0
    elif chg >= 25.0:
        tier, sl, tp = MOMENTUM_MEDIUM, 6.0, 10.0
    elif chg >= 15.0:
        tier, sl, tp = MOMENTUM_MEDIUM, 5.5, 12.0
    elif chg >= 8.0:
        tier, sl, tp = MOMENTUM_WEAK, 5.0, 14.0
    else:
        tier, sl, tp = MOMENTUM_WEAK, 5.0, 12.0

    ns = float(news_score or 0.0)
    if ns >= 50.0:
        tp += 1.5
        sl += 0.5
    elif ns >= 30.0:
        tp += 0.75
        sl += 0.25
    return tier, sl, tp


def resolve_moonshot_sl_tp(
    config: AppConfig | None,
    *,
    change_24h: float = 0.0,
    news_score: float = 0.0,
    llm_confidence: float = 0.0,
) -> tuple[float, float, str]:
    """
    24h 기세·뉴스 점수로 급등주 손익절 % 산출.
    auto_exit_strength(약·중·강)과 무관.
    """
    if config is not None and not getattr(config, "moonshot_momentum_exit_enabled", True):
        sl, tp = moonshot_sl_tp(config)
        return round(sl, 2), round(tp, 2), "급등·설정"

    tier, sl, tp = _momentum_tier(change_24h, news_score)
    conf = float(llm_confidence or 0.0)
    if conf >= 70.0:
        tp += 2.0
    elif conf >= 55.0:
        tp += 1.0

    min_sl = _cfg_float(config, "moonshot_min_stop_loss_pct", 4.0)
    max_sl = _cfg_float(
        config,
        "moonshot_max_stop_loss_pct",
        _cfg_float(config, "moonshot_stop_loss_pct", 10.0),
    )
    min_tp = _cfg_float(config, "moonshot_min_take_profit_pct", 5.0)
    max_tp = _cfg_float(
        config,
        "moonshot_max_take_profit_pct",
        max(_cfg_float(config, "moonshot_take_profit_pct", 30.0), 30.0),
    )
    sl = min(max(sl, min_sl), max_sl)
    tp = min(max(tp, min_tp), max_tp)

    labels = {
        MOMENTUM_WEAK: "약기세",
        MOMENTUM_MEDIUM: "중기세",
        MOMENTUM_STRONG: "강기세",
    }
    return round(sl, 2), round(tp, 2), f"급등·{labels.get(tier, tier)}"


def moonshot_exit_profile(sl_pct: float, tp_pct: float) -> MoonshotExitProfile:
    sl = as_float(sl_pct, 6.0)
    tp = as_float(tp_pct, 20.0)
    if tp >= 25.0 or sl >= 7.5:
        key, label = MOMENTUM_STRONG, "강기세"
    elif tp >= 15.0 or sl >= 5.5:
        key, label = MOMENTUM_MEDIUM, "중기세"
    else:
        key, label = MOMENTUM_WEAK, "약기세"
    return MoonshotExitProfile(
        momentum_key=key,
        label_ko=label,
        base_sl_pct=sl,
        base_tp_pct=tp,
    )


def apply_moonshot_adaptive_exit_levels(
    pos,
    entry: float,
    price: float,
    sl_pct: float,
    tp_pct: float,
) -> None:
    """급등주 전용 넓은 추적 손절·익절 ratchet (강과 유사하나 독립)."""
    profile = moonshot_exit_profile(sl_pct, tp_pct)
    if entry <= 0 or price <= 0:
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

    if pos.trailing_high > 0:
        ratchet_tp = pos.trailing_high * (1 - profile.tp_pullback_pct)
        if pos.take_profit > 0:
            pos.take_profit = max(pos.take_profit, ratchet_tp)
        else:
            pos.take_profit = ratchet_tp

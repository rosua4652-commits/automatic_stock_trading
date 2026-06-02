"""급등(moonshot) 종목 분류 — 고변동·고거래대금."""

from __future__ import annotations

from app.models import AppConfig


def _cfg_float(config: AppConfig | None, name: str, default: float) -> float:
    if config is None:
        return default
    return float(getattr(config, name, default) or default)


def classify_moonshot(
    *,
    change_24h: float,
    volume_usdt: float,
    entry_score: float = 0.0,
    entry_ok: bool = False,
    news_score: float = 0.0,
    config: AppConfig | None = None,
) -> tuple[bool, str]:
    """
    하루 급등 가능성이 큰 종목 — 넓은 손익절·완화된 급락 감지 대상.
    24h 상승률 + 유동성 + (진입점수 또는 차트 진입) 조합.
    """
    if config is not None and not getattr(config, "moonshot_enabled", True):
        return False, ""

    min_chg = _cfg_float(config, "moonshot_min_change_24h_pct", 8.0)
    min_vol = _cfg_float(config, "moonshot_min_volume_usdt", 1_200_000.0)
    max_chg = _cfg_float(config, "moonshot_max_change_24h_pct", 85.0)
    min_score = _cfg_float(config, "moonshot_min_entry_score", 26.0)

    news_boost = False
    if config is not None and getattr(config, "news_enabled", True):
        boost_min = _cfg_float(config, "news_boost_min_score", 25.0)
        if float(news_score or 0) >= boost_min:
            news_boost = True
            min_chg = max(4.0, min_chg - 4.0)
            min_score = max(18.0, min_score - 10.0)

    chg = float(change_24h or 0.0)
    vol = max(float(volume_usdt or 0.0), 0.0)
    score = float(entry_score or 0.0)

    if chg < min_chg:
        return False, ""
    if chg > max_chg:
        return False, f"24h +{chg:.0f}% (급등 구간 상단 · 추격 제외)"
    if vol < min_vol:
        return False, (
            f"24h 거래대금 {vol / 1_000_000:.1f}M USDT "
            f"(급등 ≥{min_vol / 1_000_000:.1f}M)"
        )
    if not entry_ok and score < min_score:
        return False, f"진입점수 {score:.0f} < 급등 {min_score:.0f}"

    tag = f"급등 +{chg:.1f}% · 거래대금 {vol / 1_000_000:.1f}M"
    if news_boost:
        tag += f" · 뉴스보조 {news_score:.0f}점"
    return True, tag


def moonshot_sl_tp(config: AppConfig | None) -> tuple[float, float]:
    """급등 전용 손익절 % (설정값)."""
    sl = _cfg_float(config, "moonshot_stop_loss_pct", 6.0)
    tp = _cfg_float(config, "moonshot_take_profit_pct", 20.0)
    return sl, tp


def is_moonshot_outlook(text: str) -> bool:
    t = (text or "").lower()
    return "급등" in text or "moonshot" in t

"""급등·하락 뉴스 분류 자동 만료 — surge_active 메타 + TTL."""

from __future__ import annotations

import time
from typing import Any

from app.engine.news_signals import NewsSymbolScore, is_news_surge
from app.models import AppConfig

SURGE_ACTIVE_KEY = "surge_active"
_KIND_SURGE = "surge"
_KIND_DOWNTREND = "downtrend"


def _normalize_symbol(symbol: str) -> str:
    return (symbol or "").upper().strip()


def surge_auto_expire_enabled(config: AppConfig | None) -> bool:
    if config is None:
        return True
    return getattr(config, "surge_auto_expire_enabled", True) is not False


def surge_tag_ttl_hours(config: AppConfig | None, kind: str) -> float:
    if kind == _KIND_DOWNTREND:
        return float(getattr(config, "downtrend_tag_ttl_hours", 24.0) or 24.0)
    return float(getattr(config, "surge_tag_ttl_hours", 48.0) or 48.0)


def get_surge_active(meta: dict | None) -> dict[str, dict[str, Any]]:
    raw = (meta or {}).get(SURGE_ACTIVE_KEY)
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for sym, row in raw.items():
        if isinstance(row, dict):
            out[_normalize_symbol(sym)] = row
    return out


def _news_source_label(sc: NewsSymbolScore) -> str:
    if sc.llm_direction:
        return "llm" if sc.llm_direction in ("bullish", "bearish") else "news+llm"
    return "news"


def touch_surge_active(
    meta: dict,
    symbol: str,
    kind: str,
    *,
    source: str = "news",
    headline: str = "",
    config: AppConfig | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """분류 갱신 — 동일 종목 신규 기사 시 since·expires_at 리셋."""
    sym = _normalize_symbol(symbol)
    if not sym or kind not in (_KIND_SURGE, _KIND_DOWNTREND):
        return {}
    ts = float(now if now is not None else time.time())
    ttl_h = surge_tag_ttl_hours(config, kind)
    expires_at = ts + ttl_h * 3600.0
    active = get_surge_active(meta)
    prev = active.get(sym) or {}
    row = {
        "kind": kind,
        "since": ts,
        "expires_at": expires_at,
        "source": str(source or prev.get("source") or "news")[:32],
        "headline": str(headline or prev.get("headline") or "")[:200],
    }
    active[sym] = row
    meta[SURGE_ACTIVE_KEY] = active
    return row


def prune_expired_surge_active(
    meta: dict,
    *,
    now: float | None = None,
    config: AppConfig | None = None,
) -> int:
    """만료 항목 제거. auto_expire 꺼짐이면 prune/skip (메타 유지)."""
    if not surge_auto_expire_enabled(config):
        return 0
    ts = float(now if now is not None else time.time())
    active = get_surge_active(meta)
    if not active:
        meta.pop(SURGE_ACTIVE_KEY, None)
        return 0
    kept: dict[str, dict[str, Any]] = {}
    removed = 0
    for sym, row in active.items():
        exp = float(row.get("expires_at") or 0)
        if exp > ts:
            kept[sym] = row
        else:
            removed += 1
    if kept:
        meta[SURGE_ACTIVE_KEY] = kept
    else:
        meta.pop(SURGE_ACTIVE_KEY, None)
    return removed


def get_surge_active_entry(
    meta: dict | None, symbol: str, *, config: AppConfig | None = None
) -> dict[str, Any] | None:
    if not surge_auto_expire_enabled(config):
        return None
    sym = _normalize_symbol(symbol)
    row = get_surge_active(meta).get(sym)
    if not row:
        return None
    if float(row.get("expires_at") or 0) <= time.time():
        return None
    return row


def is_active_surge_classification(
    meta: dict | None, symbol: str, *, config: AppConfig | None = None
) -> bool:
    if not surge_auto_expire_enabled(config):
        return True
    row = get_surge_active_entry(meta, symbol, config=config)
    return bool(row and row.get("kind") == _KIND_SURGE)


def is_active_downtrend_classification(
    meta: dict | None, symbol: str, *, config: AppConfig | None = None
) -> bool:
    if not surge_auto_expire_enabled(config):
        return True
    row = get_surge_active_entry(meta, symbol, config=config)
    return bool(row and row.get("kind") == _KIND_DOWNTREND)


def effective_is_news_surge(
    score: NewsSymbolScore | None,
    symbol: str,
    meta: dict | None,
    config: AppConfig | None,
) -> bool:
    if not is_news_surge(score, config):
        return False
    if meta is None or not surge_auto_expire_enabled(config):
        return True
    return is_active_surge_classification(meta, symbol, config=config)


def effective_news_score_for_moonshot(
    score: NewsSymbolScore | None,
    symbol: str,
    meta: dict | None,
    config: AppConfig | None,
) -> float:
    if not effective_is_news_surge(score, symbol, meta, config):
        return 0.0
    return float(score.score if score else 0.0)


def feed_tier_active(
    tier: str,
    symbol: str,
    meta: dict | None,
    config: AppConfig | None,
) -> bool:
    """뉴스 피드·관리 탭 — 만료된 surge/downtrend 제외."""
    if tier in ("surge", "news_surge"):
        if meta is None or not surge_auto_expire_enabled(config):
            return True
        return is_active_surge_classification(meta, symbol, config=config)
    if tier == "downtrend":
        if meta is None or not surge_auto_expire_enabled(config):
            return True
        return is_active_downtrend_classification(meta, symbol, config=config)
    return True


def sync_surge_active_from_news(
    meta: dict,
    scores: dict[str, NewsSymbolScore],
    config: AppConfig | None,
) -> int:
    """뉴스 갱신 후 surge_active 동기화 — 관련 기사 있으면 TTL 연장."""
    from app.engine.news_feed import classify_feed_tier

    if not surge_auto_expire_enabled(config):
        return 0
    touched = 0
    for sym, sc in scores.items():
        tier = classify_feed_tier(sc, config)
        if tier in ("surge", "news_surge"):
            touch_surge_active(
                meta,
                sym,
                _KIND_SURGE,
                source=_news_source_label(sc),
                headline=sc.headline,
                config=config,
            )
            touched += 1
        elif tier == "downtrend":
            touch_surge_active(
                meta,
                sym,
                _KIND_DOWNTREND,
                source=_news_source_label(sc),
                headline=sc.headline,
                config=config,
            )
            touched += 1
    prune_expired_surge_active(meta, config=config)
    return touched


def surge_active_fields_for_ui(
    meta: dict | None, symbol: str, *, config: AppConfig | None = None
) -> dict[str, Any]:
    row = get_surge_active_entry(meta, symbol, config=config)
    if not row:
        return {}
    since = float(row.get("since") or 0)
    expires_at = float(row.get("expires_at") or 0)
    return {
        "classified_at": since,
        "expires_at": expires_at,
        "classified_source": str(row.get("source") or ""),
        "active_headline": str(row.get("headline") or ""),
    }

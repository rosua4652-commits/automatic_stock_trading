"""뉴스 피드 API — 캐시 점수·급등/하락 분류."""

from __future__ import annotations

import time
from typing import Any

from app.engine.news_llm import _gemini_api_key, _llm_enabled, _resolve_provider, bearish_block_threshold
from app.engine.news_signals import (
    NewsSymbolScore,
    clear_news_cache,
    is_news_surge,
    refresh_news_scores,
)
from app.market.coin_registry import coin_meta
from app.models import AppConfig

_TIER_SURGE = "surge"
_TIER_NEWS_SURGE = "news_surge"
_TIER_DOWNTREND = "downtrend"
_TIER_OTHER = "other"


def _llm_direction_ko(direction: str) -> str:
    d = (direction or "").lower()
    if d == "bullish":
        return "상승"
    if d == "bearish":
        return "하락"
    return "중립"


def classify_feed_tier(sc: NewsSymbolScore, config: AppConfig | None) -> str:
    if config is not None and not getattr(config, "news_enabled", True):
        return _TIER_OTHER
    if sc.llm_direction == "bearish":
        if sc.llm_confidence >= bearish_block_threshold(config):
            return _TIER_DOWNTREND
    if sc.sentiment == "negative" and sc.score >= 15:
        return _TIER_DOWNTREND
    if is_news_surge(sc, config):
        if sc.llm_direction == "bullish" or sc.score >= 45:
            return _TIER_SURGE
        return _TIER_NEWS_SURGE
    if sc.llm_direction == "bullish" and sc.score >= 18:
        return _TIER_SURGE
    return _TIER_OTHER


def _tier_label_ko(tier: str) -> str:
    if tier == _TIER_SURGE:
        return "급등"
    if tier == _TIER_NEWS_SURGE:
        return "뉴스급등"
    if tier == _TIER_DOWNTREND:
        return "하락주"
    return "기타"


def llm_status_payload(config: AppConfig) -> dict[str, Any]:
    enabled = bool(getattr(config, "news_llm_enabled", False))
    provider = str(getattr(config, "news_llm_provider", "gemini") or "gemini")
    key_ok = bool(_gemini_api_key(config))
    active = _llm_enabled(config)
    resolved = _resolve_provider(config) if enabled else None
    return {
        "enabled": enabled,
        "active": active,
        "provider": resolved or provider,
        "key_configured": key_ok,
        "hint": (
            "Gemini 연동 중"
            if active
            else (
                "API 키 필요 (설정 > Gemini API 키)"
                if enabled and not key_ok
                else "키워드 점수만 (AI 꺼짐 또는 키 없음)"
            )
        ),
    }


def _score_item(sym: str, sc: NewsSymbolScore, config: AppConfig) -> dict[str, Any]:
    meta = coin_meta(sym)
    tier = classify_feed_tier(sc, config)
    pub_ts = float(sc.published_ts or 0)
    return {
        "symbol": sym.upper(),
        "base": meta["base"],
        "name_ko": meta["name_ko"],
        "score": sc.score,
        "count": sc.count,
        "sentiment": sc.sentiment,
        "keywords": sc.keywords,
        "headline": sc.headline,
        "url": sc.url or "",
        "tag": sc.tag,
        "published_ts": pub_ts,
        "published_at": (
            time.strftime("%Y-%m-%d %H:%M", time.localtime(pub_ts))
            if pub_ts > 0
            else ""
        ),
        "article_source": sc.source or "",
        "llm_direction": sc.llm_direction,
        "llm_direction_ko": _llm_direction_ko(sc.llm_direction),
        "llm_confidence": sc.llm_confidence,
        "llm_reason": sc.llm_reason,
        "tier": tier,
        "tier_label": _tier_label_ko(tier),
    }


def _cached_scores() -> dict[str, NewsSymbolScore]:
    from app.engine.news_signals import _cache

    raw = _cache.get("scores")
    if not isinstance(raw, dict):
        return {}
    return {k.upper(): v for k, v in raw.items() if isinstance(v, NewsSymbolScore)}


def _feed_item_visible(
    tier: str, symbol: str, meta: dict | None, config: AppConfig
) -> bool:
    from app.engine.surge_tag_expiry import feed_tier_active

    return feed_tier_active(tier, symbol, meta, config)


def build_news_feed(config: AppConfig, meta: dict | None = None) -> dict[str, Any]:
    from app.engine.news_signals import _cache

    scores = _cached_scores()
    items = [
        _score_item(sym, sc, config)
        for sym, sc in sorted(scores.items(), key=lambda x: -x[1].score)
    ]
    surge = [
        i
        for i in items
        if i["tier"] in (_TIER_SURGE, _TIER_NEWS_SURGE)
        and _feed_item_visible(i["tier"], i["symbol"], meta, config)
    ]
    downtrend = [
        i
        for i in items
        if i["tier"] == _TIER_DOWNTREND
        and _feed_item_visible(i["tier"], i["symbol"], meta, config)
    ]
    return {
        "ok": True,
        "cache_ok": bool(_cache.get("ok")),
        "refreshed_at": float(_cache.get("ts") or 0),
        "news_enabled": getattr(config, "news_enabled", True) is not False,
        "llm_status": llm_status_payload(config),
        "items": items,
        "surge": surge,
        "downtrend": downtrend,
        "surge_count": len(surge),
        "downtrend_count": len(downtrend),
    }


async def refresh_news_feed(
    config: AppConfig,
    symbols: list[str],
    *,
    force: bool = False,
) -> dict[str, Any]:
    if force:
        clear_news_cache()
    syms = [s.upper() for s in symbols if s]
    if not syms:
        from app.market.scanner import top_usdt_symbols

        syms = await top_usdt_symbols(limit=40)
    await refresh_news_scores(syms, config)
    from app.engine.portfolio_store import store
    from app.engine.surge_tag_expiry import sync_surge_active_from_news

    sync_surge_active_from_news(store._live_meta, _cached_scores(), config)
    store.save_live_meta()
    out = build_news_feed(config, meta=store._live_meta)
    out["refreshed"] = True
    out["symbol_count"] = len(syms)
    return out

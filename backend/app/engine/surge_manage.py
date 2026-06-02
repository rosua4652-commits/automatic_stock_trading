"""급등·하락 분류 관리 — 비활성 목록·태그 동기화."""

from __future__ import annotations

import time
from typing import Any

from app.engine.news_feed import classify_feed_tier
from app.engine.news_signals import NewsSymbolScore, get_cached_news_score
from app.engine.news_signals import is_news_surge
from app.engine.surge_classifier import classify_moonshot
from app.engine.surge_tag_expiry import (
    effective_is_news_surge,
    feed_tier_active,
    get_surge_active,
    get_surge_active_entry,
    prune_expired_surge_active,
    surge_active_fields_for_ui,
    surge_auto_expire_enabled,
    sync_surge_active_from_news,
)
from app.market.coin_registry import coin_meta
from app.models import AppConfig, CoinCandidate, InvestmentRecommendation

_META_KEY = "disabled_surge_symbols"


def _normalize_symbol(symbol: str) -> str:
    return (symbol or "").upper().strip()


def get_disabled_symbols(meta: dict | None) -> set[str]:
    raw = (meta or {}).get(_META_KEY) or []
    if not isinstance(raw, list):
        return set()
    return {_normalize_symbol(s) for s in raw if s}


def disable_surge_symbol(meta: dict, symbol: str, *, reason: str = "") -> list[str]:
    sym = _normalize_symbol(symbol)
    if not sym:
        return list(get_disabled_symbols(meta))
    disabled = get_disabled_symbols(meta)
    disabled.add(sym)
    meta[_META_KEY] = sorted(disabled)
    if reason:
        reasons = meta.setdefault("disabled_surge_reasons", {})
        if isinstance(reasons, dict):
            reasons[sym] = str(reason)[:200]
    return meta[_META_KEY]


def enable_surge_symbol(meta: dict, symbol: str) -> list[str]:
    sym = _normalize_symbol(symbol)
    disabled = get_disabled_symbols(meta)
    disabled.discard(sym)
    meta[_META_KEY] = sorted(disabled)
    reasons = meta.get("disabled_surge_reasons")
    if isinstance(reasons, dict):
        reasons.pop(sym, None)
    return meta[_META_KEY]


def _source_label(
    *,
    news_tier: str,
    is_moon: bool,
    ns: NewsSymbolScore | None,
    config: AppConfig | None = None,
) -> str:
    if is_moon and ns and is_news_surge(ns, config):
        return "가격+뉴스"
    if is_moon:
        return "가격"
    if ns and ns.llm_direction:
        return "뉴스+LLM"
    if news_tier in ("surge", "news_surge", "downtrend"):
        return "뉴스"
    return "기타"


def sync_surge_tags(
    *,
    recommendations: list[InvestmentRecommendation],
    candidates: list[CoinCandidate],
    config: AppConfig,
    disabled: set[str] | None = None,
    meta: dict | None = None,
) -> dict[str, str]:
    """심볼별 surge|downtrend 태그 — UI 배지용."""
    disabled = disabled or set()
    tags: dict[str, str] = {}
    cand_map = {c.symbol.upper(): c for c in candidates}

    from app.engine.news_signals import _cache

    raw = _cache.get("scores")
    scores: dict[str, NewsSymbolScore] = {}
    if isinstance(raw, dict):
        scores = {k.upper(): v for k, v in raw.items() if isinstance(v, NewsSymbolScore)}

    for sym, sc in scores.items():
        if sym in disabled:
            continue
        tier = classify_feed_tier(sc, config)
        if tier in ("surge", "news_surge"):
            if feed_tier_active(tier, sym, meta, config):
                tags[sym] = "surge"
        elif tier == "downtrend":
            if feed_tier_active(tier, sym, meta, config):
                tags[sym] = "downtrend"

    for r in recommendations:
        sym = r.symbol.upper()
        if sym in disabled:
            tags.pop(sym, None)
            continue
        if (r.entry_tier or "").lower() == "moonshot":
            tags[sym] = "surge"

    for sym, c in cand_map.items():
        if sym in disabled or sym in tags:
            continue
        ns = scores.get(sym) or get_cached_news_score(sym)
        news_pts = float(
            ns.score
            if ns and effective_is_news_surge(ns, sym, meta, config)
            else 0.0
        )
        is_moon, _ = classify_moonshot(
            change_24h=c.change_24h,
            volume_usdt=float(getattr(c, "volume_usdt", 0) or 0),
            entry_score=c.entry_score,
            entry_ok=c.entry_ok,
            news_score=news_pts,
            config=config,
        )
        if is_moon:
            tags[sym] = "surge"

    if meta and surge_auto_expire_enabled(config):
        for sym in get_surge_active(meta):
            if sym in disabled:
                tags.pop(sym, None)
                continue
            entry = get_surge_active_entry(meta, sym, config=config)
            if not entry:
                continue
            kind = str(entry.get("kind") or "")
            if kind in ("surge", "downtrend"):
                tags[sym] = kind

    return tags


def build_surge_manage_payload(
    *,
    config: AppConfig,
    recommendations: list[InvestmentRecommendation],
    candidates: list[CoinCandidate],
    meta: dict,
) -> dict[str, Any]:
    prune_expired_surge_active(meta, config=config)
    disabled = get_disabled_symbols(meta)
    cand_map = {c.symbol.upper(): c for c in candidates}
    rec_map = {r.symbol.upper(): r for r in recommendations}

    from app.engine.news_signals import _cache

    raw = _cache.get("scores")
    scores: dict[str, NewsSymbolScore] = {}
    if isinstance(raw, dict):
        scores = {k.upper(): v for k, v in raw.items() if isinstance(v, NewsSymbolScore)}

    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _append(sym: str, *, tag: str, tier: str, source: str, sc: NewsSymbolScore | None, rec: InvestmentRecommendation | None):
        if sym in seen:
            return
        seen.add(sym)
        meta_coin = coin_meta(sym)
        cand = cand_map.get(sym)
        is_moon = rec and (rec.entry_tier or "").lower() == "moonshot"
        items.append(
            {
                "symbol": sym,
                "base": meta_coin["base"],
                "name_ko": meta_coin["name_ko"],
                "tag": tag,
                "tier": tier,
                "tier_label": "급등" if tag == "surge" else "하락주",
                "source": source,
                "score": float(sc.score if sc else (rec.news_score if rec else 0) or 0),
                "headline": (sc.headline if sc else "") or (rec.news_detail if rec else "") or "",
                "url": (sc.url if sc else "") or (rec.news_url if rec else "") or "",
                "published_ts": float(sc.published_ts if sc else 0),
                "article_source": (sc.source if sc else "") or "",
                "llm_direction": (sc.llm_direction if sc else "") or "",
                "llm_confidence": float(sc.llm_confidence if sc else 0),
                "llm_reason": (sc.llm_reason if sc else "") or "",
                "change_24h": float(
                    (rec.change_24h if rec else 0)
                    or (cand.change_24h if cand else 0)
                ),
                "disabled": sym in disabled,
                "disabled_reason": (meta.get("disabled_surge_reasons") or {}).get(sym, "")
                if isinstance(meta.get("disabled_surge_reasons"), dict)
                else "",
                **surge_active_fields_for_ui(meta, sym, config=config),
            }
        )

    for sym, sc in sorted(scores.items(), key=lambda x: -x[1].score):
        tier = classify_feed_tier(sc, config)
        if tier not in ("surge", "news_surge", "downtrend"):
            continue
        if not feed_tier_active(tier, sym, meta, config):
            continue
        tag = "surge" if tier in ("surge", "news_surge") else "downtrend"
        rec = rec_map.get(sym)
        cand = cand_map.get(sym)
        is_moon = bool(rec and (rec.entry_tier or "").lower() == "moonshot")
        if not is_moon and cand:
            news_pts = float(
                sc.score if effective_is_news_surge(sc, sym, meta, config) else 0.0
            )
            is_moon, _ = classify_moonshot(
                change_24h=cand.change_24h,
                volume_usdt=float(getattr(cand, "volume_usdt", 0) or 0),
                entry_score=cand.entry_score,
                entry_ok=cand.entry_ok,
                news_score=news_pts,
                config=config,
            )
        _append(
            sym,
            tag=tag,
            tier=tier,
            source=_source_label(news_tier=tier, is_moon=is_moon, ns=sc, config=config),
            sc=sc,
            rec=rec,
        )

    for sym, rec in rec_map.items():
        if (rec.entry_tier or "").lower() != "moonshot":
            continue
        sc = scores.get(sym)
        _append(
            sym,
            tag="surge",
            tier="moonshot",
            source=_source_label(
                news_tier=classify_feed_tier(sc, config) if sc else "",
                is_moon=True,
                ns=sc,
                config=config,
            ),
            sc=sc,
            rec=rec,
        )

    if surge_auto_expire_enabled(config):
        for sym, row in get_surge_active(meta).items():
            if sym in seen or sym in disabled:
                continue
            entry = get_surge_active_entry(meta, sym, config=config)
            if not entry:
                continue
            kind = str(entry.get("kind") or "")
            if kind not in ("surge", "downtrend"):
                continue
            sc = scores.get(sym)
            rec = rec_map.get(sym)
            tier = kind if sc is None else classify_feed_tier(sc, config)
            _append(
                sym,
                tag=kind,
                tier=tier,
                source=str(entry.get("source") or "news")[:32],
                sc=sc,
                rec=rec,
            )

    surge = [i for i in items if i["tag"] == "surge" and not i["disabled"]]
    downtrend = [i for i in items if i["tag"] == "downtrend" and not i["disabled"]]
    disabled_items = [i for i in items if i["disabled"]]

    from app.engine.news_signals import _cache as news_cache

    cache_ts = 0.0
    if isinstance(news_cache, dict):
        cache_ts = float(news_cache.get("ts") or 0)

    return {
        "ok": True,
        "refreshed_at": cache_ts or time.time(),
        "items": items,
        "surge": surge,
        "downtrend": downtrend,
        "disabled": disabled_items,
        "surge_count": len(surge),
        "downtrend_count": len(downtrend),
        "disabled_count": len(disabled_items),
        "disabled_symbols": sorted(disabled),
    }

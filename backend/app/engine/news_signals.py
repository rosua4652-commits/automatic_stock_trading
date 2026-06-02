"""뉴스·기사 기반 급등 보조 신호 — 키워드 + (선택) LLM 방향 판단."""

from __future__ import annotations

import asyncio
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime

import httpx

from app.market.coin_registry import COIN_NAMES
from app.models import AppConfig

logger = logging.getLogger(__name__)

RSS_FEEDS = (
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
)

SURGE_KEYWORDS: tuple[str, ...] = (
    "listing",
    "partnership",
    "burn",
    "etf",
    "approval",
    "approved",
    "launch",
    "mainnet",
    "upgrade",
    "airdrop",
    "surge",
    "rally",
    "breakout",
    "record high",
    "all-time high",
    "ath",
    "상장",
    "파트너",
    "소각",
    "승인",
    "급등",
)

POSITIVE_KEYWORDS: tuple[str, ...] = (
    "partnership",
    "listing",
    "approval",
    "approved",
    "launch",
    "upgrade",
    "adoption",
    "investment",
    "surge",
    "rally",
    "breakout",
    "record",
    "growth",
    "상장",
    "승인",
    "투자",
    "급등",
)

NEGATIVE_KEYWORDS: tuple[str, ...] = (
    "hack",
    "hacked",
    "exploit",
    "scam",
    "fraud",
    "lawsuit",
    "sec charge",
    "ban",
    "delist",
    "bankrupt",
    "collapse",
    "crash",
    "plunge",
    "해킹",
    "사기",
    "규제",
    "폭락",
)

_cache: dict[str, object] = {"ts": 0.0, "scores": {}, "ok": False}


@dataclass
class NewsArticle:
    title: str
    source: str
    published_ts: float = 0.0
    snippet: str = ""
    url: str = ""


@dataclass
class NewsSymbolScore:
    score: float = 0.0
    count: int = 0
    sentiment: str = "neutral"
    keywords: list[str] = field(default_factory=list)
    headline: str = ""
    tag: str = ""
    published_ts: float = 0.0
    source: str = ""
    url: str = ""
    llm_direction: str = ""
    llm_confidence: float = 0.0
    llm_reason: str = ""


def _cfg_float(config: AppConfig | None, name: str, default: float) -> float:
    if config is None:
        return default
    return float(getattr(config, name, default) or default)


def _cfg_int(config: AppConfig | None, name: str, default: int) -> int:
    if config is None:
        return default
    return int(getattr(config, name, default) or default)


def _build_alias_map() -> dict[str, str]:
    aliases: dict[str, str] = {}
    extras = {
        "bitcoin": "BTC",
        "ethereum": "ETH",
        "solana": "SOL",
        "ripple": "XRP",
        "dogecoin": "DOGE",
        "shiba": "SHIB",
        "pepe": "PEPE",
    }
    for base, (ko, en) in COIN_NAMES.items():
        aliases[base.lower()] = base
        aliases[en.lower()] = base
        if ko:
            aliases[ko.lower()] = base
    aliases.update(extras)
    return aliases


_ALIAS_MAP = _build_alias_map()
_ALIAS_SORTED = sorted(_ALIAS_MAP.items(), key=lambda x: len(x[0]), reverse=True)


def _parse_rss_ts(raw: str) -> float:
    if not raw:
        return time.time()
    try:
        return parsedate_to_datetime(raw.strip()).timestamp()
    except Exception:
        return time.time()


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _parse_rss_xml(text: str, source: str) -> list[NewsArticle]:
    out: list[NewsArticle] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return out
    for item in root.iter():
        if _strip_ns(item.tag) != "item":
            continue
        title = ""
        pub = ""
        snippet = ""
        link = ""
        for child in item:
            name = _strip_ns(child.tag)
            if name == "title" and child.text:
                title = child.text.strip()
            elif name == "link":
                href = (child.get("href") or "").strip()
                text = (child.text or "").strip()
                link = href or text
            elif name in ("description", "summary", "content") and child.text:
                snippet = child.text.strip()[:500]
            elif name in ("pubDate", "published", "updated") and child.text:
                pub = child.text.strip()
        if title:
            out.append(
                NewsArticle(
                    title=title,
                    source=source,
                    published_ts=_parse_rss_ts(pub),
                    snippet=snippet,
                    url=link,
                )
            )
    return out


def _match_bases(text: str) -> set[str]:
    low = (text or "").lower()
    found: set[str] = set()
    for alias, base in _ALIAS_SORTED:
        if len(alias) < 2:
            continue
        if alias.isalpha() and len(alias) <= 5:
            if re.search(rf"\b{re.escape(alias)}\b", low):
                found.add(base)
        elif alias in low:
            found.add(base)
    return found


def _keyword_hits(text: str, keywords: tuple[str, ...]) -> list[str]:
    low = (text or "").lower()
    return [k for k in keywords if k in low]


def score_articles_for_base(base: str, articles: list[NewsArticle]) -> NewsSymbolScore:
    """규칙 기반 뉴스 점수 (0~100)."""
    now = time.time()
    recent = [a for a in articles if now - a.published_ts <= 86_400]
    if not recent:
        return NewsSymbolScore()

    count = len(recent)
    score = min(28.0, count * 7.0)
    kw_set: set[str] = set()
    pos = neg = 0
    top = recent[0]

    for art in recent:
        hits = _keyword_hits(art.title, SURGE_KEYWORDS)
        kw_set.update(hits)
        score += min(12.0, len(hits) * 4.0)
        pos += len(_keyword_hits(art.title, POSITIVE_KEYWORDS))
        neg += len(_keyword_hits(art.title, NEGATIVE_KEYWORDS))

    if pos > neg:
        score += 10.0
        sentiment = "positive"
    elif neg > pos:
        score -= 12.0
        sentiment = "negative"
    else:
        sentiment = "neutral"

    score = max(0.0, min(100.0, score))
    kws = sorted(kw_set)[:4]
    tag_parts = [f"뉴스 {count}건"]
    if kws:
        tag_parts.append(" · ".join(kws[:2]))
    tag = " · ".join(tag_parts)
    if score >= 25:
        tag = f"뉴스급등 {score:.0f}점 · {tag}"

    return NewsSymbolScore(
        score=round(score, 1),
        count=count,
        sentiment=sentiment,
        keywords=kws,
        headline=top.title[:120],
        tag=tag,
        published_ts=float(top.published_ts or 0),
        source=str(top.source or ""),
        url=str(top.url or ""),
    )


def is_news_surge(score: NewsSymbolScore | None, config: AppConfig | None) -> bool:
    if config is not None and not getattr(config, "news_enabled", True):
        return False
    if not score or score.score <= 0:
        return False
    if score.llm_direction == "bearish":
        from app.engine.news_llm import bearish_block_threshold

        if score.llm_confidence >= bearish_block_threshold(config):
            return False
    if score.sentiment == "negative" and score.score < 40:
        return False
    return score.score >= _cfg_float(config, "news_boost_min_score", 25.0)


async def _fetch_rss(client: httpx.AsyncClient, name: str, url: str) -> list[NewsArticle]:
    try:
        resp = await client.get(url, timeout=12.0)
        if resp.status_code != 200:
            return []
        return _parse_rss_xml(resp.text, name)
    except Exception as exc:
        logger.debug("RSS %s fetch failed: %s", name, exc)
        return []


async def _fetch_coingecko_trending(
    client: httpx.AsyncClient,
) -> list[NewsArticle]:
    try:
        resp = await client.get(
            "https://api.coingecko.com/api/v3/search/trending",
            timeout=12.0,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        now = time.time()
        out: list[NewsArticle] = []
        for row in data.get("coins") or []:
            item = row.get("item") or {}
            sym = str(item.get("symbol") or "").upper()
            name = str(item.get("name") or sym)
            coin_id = str(item.get("id") or "").strip()
            if not sym:
                continue
            cg_url = (
                f"https://www.coingecko.com/en/coins/{coin_id}" if coin_id else ""
            )
            out.append(
                NewsArticle(
                    title=f"CoinGecko trending: {name} ({sym}) surge interest",
                    source="CoinGecko",
                    published_ts=now,
                    url=cg_url,
                )
            )
        return out
    except Exception as exc:
        logger.debug("CoinGecko trending failed: %s", exc)
        return []


async def _fetch_cryptopanic(
    client: httpx.AsyncClient,
    api_key: str,
) -> list[NewsArticle]:
    key = (api_key or "").strip()
    if not key:
        return []
    try:
        resp = await client.get(
            "https://cryptopanic.com/api/v1/posts/",
            params={"auth_token": key, "public": "true", "kind": "news"},
            timeout=12.0,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        out: list[NewsArticle] = []
        for row in data.get("results") or []:
            title = str(row.get("title") or "").strip()
            if not title:
                continue
            ts_raw = row.get("published_at") or row.get("created_at")
            ts = time.time()
            if ts_raw:
                try:
                    ts = parsedate_to_datetime(str(ts_raw).replace("Z", "+00:00")).timestamp()
                except Exception:
                    pass
            src = "CryptoPanic"
            currencies = row.get("currencies") or []
            if currencies:
                codes = ", ".join(
                    str(c.get("code") or "").upper()
                    for c in currencies
                    if c.get("code")
                )
                if codes:
                    title = f"{title} [{codes}]"
            url = str(row.get("url") or "").strip()
            out.append(
                NewsArticle(title=title, source=src, published_ts=ts, url=url)
            )
        return out
    except Exception as exc:
        logger.debug("CryptoPanic fetch failed: %s", exc)
        return []


async def _fetch_all_articles(config: AppConfig | None) -> list[NewsArticle]:
    headers = {"User-Agent": "AIDI/1.0 (news-signals)"}
    async with httpx.AsyncClient(timeout=15.0, headers=headers, trust_env=True) as client:
        tasks = [
            _fetch_rss(client, name, url) for name, url in RSS_FEEDS
        ]
        tasks.append(_fetch_coingecko_trending(client))
        cp_key = getattr(config, "cryptopanic_api_key", "") if config else ""
        tasks.append(_fetch_cryptopanic(client, cp_key or ""))
        parts = await asyncio.gather(*tasks, return_exceptions=True)
        articles: list[NewsArticle] = []
        for part in parts:
            if isinstance(part, list):
                articles.extend(part)
        return articles


def _articles_by_base(articles: list[NewsArticle]) -> dict[str, list[NewsArticle]]:
    by_base: dict[str, list[NewsArticle]] = {}
    for art in articles:
        bases = _match_bases(art.title)
        for base in bases:
            by_base.setdefault(base, []).append(art)
    for base in by_base:
        by_base[base].sort(key=lambda a: a.published_ts, reverse=True)
    return by_base


def _score_map_for_symbols(
    symbols: list[str],
    by_base: dict[str, list[NewsArticle]],
) -> dict[str, NewsSymbolScore]:
    out: dict[str, NewsSymbolScore] = {}
    for sym in symbols:
        base = sym.upper().replace("USDT", "").replace("USD", "")
        arts = by_base.get(base, [])
        sc = score_articles_for_base(base, arts)
        if sc.score > 0:
            out[sym.upper()] = sc
    return out


async def refresh_news_scores(
    symbols: list[str],
    config: AppConfig | None = None,
) -> dict[str, NewsSymbolScore]:
    """스캔 루프용 — TTL 캐시 후 심볼별 점수 반환."""
    if config is not None and not getattr(config, "news_enabled", True):
        return {}

    ttl = _cfg_int(config, "news_cache_ttl_sec", 420)
    now = time.time()
    cached_scores = _cache.get("scores")
    if (
        _cache.get("ok")
        and isinstance(cached_scores, dict)
        and now - float(_cache.get("ts") or 0) < ttl
    ):
        return {
            s.upper(): cached_scores[s.upper()]
            for s in symbols
            if s.upper() in cached_scores
        }

    try:
        articles = await _fetch_all_articles(config)
        bases_needed = {s.upper().replace("USDT", "").replace("USD", "") for s in symbols}
        by_base = _articles_by_base(articles)
        all_scores: dict[str, NewsSymbolScore] = {}
        for base in bases_needed:
            sym = f"{base}USDT"
            sc = score_articles_for_base(base, by_base.get(base, []))
            if sc.score > 0:
                all_scores[sym] = sc
        from app.engine.news_llm import enrich_scores_with_llm

        all_scores = await enrich_scores_with_llm(all_scores, by_base, config)
        _cache["ts"] = now
        _cache["scores"] = all_scores
        _cache["ok"] = True
        return {s.upper(): all_scores[s.upper()] for s in symbols if s.upper() in all_scores}
    except Exception as exc:
        logger.warning("News refresh failed (price-only fallback): %s", exc)
        return {
            s.upper(): cached_scores[s.upper()]
            for s in symbols
            if isinstance(cached_scores, dict) and s.upper() in cached_scores
        }


def get_cached_news_score(symbol: str) -> NewsSymbolScore | None:
    cached = _cache.get("scores")
    if not isinstance(cached, dict):
        return None
    return cached.get(symbol.upper())


def clear_news_cache() -> None:
    _cache.clear()
    _cache.update({"ts": 0.0, "scores": {}, "ok": False})
    from app.engine.news_llm import clear_llm_cache

    clear_llm_cache()

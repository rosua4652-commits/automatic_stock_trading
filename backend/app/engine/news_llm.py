"""뉴스 헤드라인 LLM 방향 판단 — 키워드 오판(급등 표기·실제 하락) 보정."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass

import httpx

from app.engine.news_signals import NewsArticle, NewsSymbolScore, _cfg_int
from app.models import AppConfig

logger = logging.getLogger(__name__)

_LLM_CACHE: dict[str, tuple[float, "ArticleLlmResult"]] = {}
_LLM_KEY_WARNED = False

SYSTEM_PROMPT = (
    "암호화폐 뉴스 헤드라인의 실제 시장 방향을 판단하세요. "
    "제목에 '급등'·'surge'·'rally'가 있어도 맥락상 하락·부정·리스크면 bearish입니다. "
    "JSON만 출력: "
    '{"direction":"bullish|bearish|neutral","confidence":0-100,"reason_ko":"한 줄 한국어"}'
)


@dataclass
class ArticleLlmResult:
    direction: str = "neutral"
    confidence: int = 0
    reason: str = ""


def _article_hash(title: str, snippet: str = "") -> str:
    raw = f"{(title or '').strip()}|{(snippet or '').strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _gemini_api_key(config: AppConfig | None) -> str:
    if config is None:
        return ""
    return (
        (getattr(config, "news_llm_api_key", "") or "").strip()
        or (getattr(config, "gemini_api_key", "") or "").strip()
    )


def bearish_block_threshold(config: AppConfig | None) -> int:
    if config is None:
        return 60
    return int(getattr(config, "news_llm_bearish_block_threshold", 60) or 60)


def _resolve_provider(config: AppConfig) -> str | None:
    provider = str(getattr(config, "news_llm_provider", "gemini") or "gemini").lower()
    openai_key = (getattr(config, "openai_api_key", "") or "").strip()
    gemini_key = _gemini_api_key(config)
    if provider == "openai":
        return "openai" if openai_key else None
    if provider == "gemini":
        return "gemini" if gemini_key else None
    if gemini_key:
        return "gemini"
    if openai_key:
        return "openai"
    return None


def _maybe_warn_missing_key(config: AppConfig | None) -> None:
    global _LLM_KEY_WARNED
    if _LLM_KEY_WARNED or config is None:
        return
    if not getattr(config, "news_llm_enabled", False):
        return
    if _resolve_provider(config):
        return
    _LLM_KEY_WARNED = True
    logger.info(
        "News LLM enabled but no Gemini API key — keyword-only mode "
        "(설정 > 뉴스 AI 판단 > Gemini API 키)"
    )


def _llm_enabled(config: AppConfig | None) -> bool:
    if config is None or not getattr(config, "news_llm_enabled", False):
        return False
    if not _resolve_provider(config):
        _maybe_warn_missing_key(config)
        return False
    return True


def _parse_llm_json(text: str) -> ArticleLlmResult:
    raw = (text or "").strip()
    if not raw:
        return ArticleLlmResult()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if not m:
            return ArticleLlmResult()
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return ArticleLlmResult()
    direction = str(data.get("direction") or "neutral").lower()
    if direction not in ("bullish", "bearish", "neutral"):
        direction = "neutral"
    try:
        confidence = int(float(data.get("confidence") or 0))
    except (TypeError, ValueError):
        confidence = 0
    confidence = max(0, min(100, confidence))
    reason = str(data.get("reason_ko") or data.get("reason") or "").strip()[:120]
    return ArticleLlmResult(direction=direction, confidence=confidence, reason=reason)


def _user_prompt(article: NewsArticle) -> str:
    parts = [f"제목: {article.title}"]
    if article.snippet:
        parts.append(f"요약: {article.snippet[:400]}")
    parts.append(f"출처: {article.source}")
    return "\n".join(parts)


async def _call_openai(
    client: httpx.AsyncClient,
    api_key: str,
    article: NewsArticle,
) -> ArticleLlmResult:
    resp = await client.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "gpt-4o-mini",
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(article)},
            ],
        },
        timeout=20.0,
    )
    resp.raise_for_status()
    content = (
        resp.json()
        .get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    return _parse_llm_json(content)


async def _call_gemini(
    client: httpx.AsyncClient,
    api_key: str,
    article: NewsArticle,
) -> ArticleLlmResult:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )
    resp = await client.post(
        url,
        json={
            "contents": [{"parts": [{"text": f"{SYSTEM_PROMPT}\n\n{_user_prompt(article)}"}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        },
        timeout=20.0,
    )
    resp.raise_for_status()
    parts = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = parts[0].get("text", "") if parts else ""
    return _parse_llm_json(text)


async def analyze_article(
    client: httpx.AsyncClient,
    article: NewsArticle,
    config: AppConfig | None,
    *,
    ttl_sec: int = 420,
) -> ArticleLlmResult:
    """단일 기사 LLM 분석 (해시 캐시, 실패 시 neutral)."""
    if config is None:
        return ArticleLlmResult()
    provider = _resolve_provider(config)
    if not provider:
        _maybe_warn_missing_key(config)
        return ArticleLlmResult()

    h = _article_hash(article.title, article.snippet)
    now = time.time()
    cached = _LLM_CACHE.get(h)
    if cached and now - cached[0] < ttl_sec:
        return cached[1]

    api_key = (
        (config.openai_api_key or "").strip()
        if provider == "openai"
        else _gemini_api_key(config)
    )
    if not api_key:
        return ArticleLlmResult()

    try:
        if provider == "openai":
            result = await _call_openai(client, api_key, article)
        else:
            result = await _call_gemini(client, api_key, article)
    except Exception as exc:
        logger.debug("News LLM failed (%s): %s", provider, exc)
        result = ArticleLlmResult()

    _LLM_CACHE[h] = (now, result)
    return result


def apply_llm_to_score(
    score: NewsSymbolScore,
    analyses: list[ArticleLlmResult],
    config: AppConfig | None = None,
) -> NewsSymbolScore:
    """키워드 점수에 LLM 방향 반영 — bearish 고신뢰 시 급등 차단·점수 하향."""
    if not analyses:
        return score

    threshold = bearish_block_threshold(config)
    dominant = max(analyses, key=lambda a: a.confidence)
    score.llm_direction = dominant.direction
    score.llm_confidence = float(dominant.confidence)
    score.llm_reason = dominant.reason

    if dominant.direction == "bearish" and dominant.confidence >= threshold:
        penalty = 20.0 + dominant.confidence * 0.25
        score.score = max(0.0, round(score.score - penalty, 1))
        score.sentiment = "negative"
        if dominant.reason:
            score.tag = f"AI하락 {dominant.confidence}% · {dominant.reason[:40]}"
    elif dominant.direction == "bullish" and dominant.confidence >= 55:
        score.score = min(100.0, round(score.score + 8.0, 1))
        if score.sentiment != "negative":
            score.sentiment = "positive"
        if dominant.reason and score.score >= 25:
            score.tag = f"AI상승 {dominant.confidence}% · {score.tag or dominant.reason[:40]}"

    return score


async def enrich_scores_with_llm(
    scores: dict[str, NewsSymbolScore],
    by_base: dict[str, list[NewsArticle]],
    config: AppConfig | None,
) -> dict[str, NewsSymbolScore]:
    """스캔당 상한 내 기사 LLM 분석 후 심볼별 점수 보정."""
    if not scores:
        return scores
    if not _llm_enabled(config):
        return scores

    ttl = _cfg_int(config, "news_cache_ttl_sec", 420)
    max_calls = _cfg_int(config, "news_llm_max_articles_per_scan", 8)

    unique: dict[str, NewsArticle] = {}
    sym_articles: dict[str, list[NewsArticle]] = {}
    for sym, sc in scores.items():
        if sc.score <= 0:
            continue
        base = sym.upper().replace("USDT", "").replace("USD", "")
        arts = by_base.get(base, [])[:3]
        if not arts:
            continue
        sym_articles[sym] = arts
        for art in arts:
            h = _article_hash(art.title, art.snippet)
            if h not in unique and len(unique) < max_calls:
                unique[h] = art

    if not unique:
        return scores

    hash_results: dict[str, ArticleLlmResult] = {}
    headers = {"User-Agent": "AIDI/1.0 (news-llm)"}
    async with httpx.AsyncClient(timeout=22.0, headers=headers, trust_env=True) as client:
        for h, art in unique.items():
            hash_results[h] = await analyze_article(client, art, config, ttl_sec=ttl)

    out = dict(scores)
    for sym, arts in sym_articles.items():
        analyses = [
            hash_results[_article_hash(a.title, a.snippet)]
            for a in arts
            if _article_hash(a.title, a.snippet) in hash_results
        ]
        if analyses:
            out[sym] = apply_llm_to_score(out[sym], analyses, config)
    return out


def clear_llm_cache() -> None:
    _LLM_CACHE.clear()

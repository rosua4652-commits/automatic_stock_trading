"""백테스트 배치 요약 → Gemini 패턴·손익절·종목 가중 제안 (뉴스 BT 아님)."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.engine.backtest_learning import (
    BacktestLearningState,
    _clamp_auto_sl_tp,
    load_learning_state,
    save_learning_state,
)
from app.engine.backtest_optimizer import BacktestAccumulator, SideStats, SymbolBacktestRecord
from app.engine.news_llm import _gemini_api_key
from app.models import AppConfig
from app.util.numbers import as_float

logger = logging.getLogger(__name__)

VALID_ACTIONS = frozenset(
    {"keep", "widen_tp", "tighten_sl", "block", "boost", "prefer_scalp", "prefer_long"}
)
VALID_SIDES = frozenset({"long", "scalp", "neutral"})

SYSTEM_PROMPT = (
    "암호화폐 백테스트(EMA 크로스·손절/익절 그리드) 결과를 보고 실전 조정을 제안하세요. "
    "과거 캔들 시뮬이며 미래 수익을 보장하지 않습니다. 보수적으로 판단하세요. "
    "JSON만 출력: "
    '{"action":"keep|widen_tp|tighten_sl|block|boost|prefer_scalp|prefer_long",'
    '"prefer_side":"long|scalp|neutral","confidence":0-100,"reason_ko":"한 줄 한국어"}'
)


@dataclass
class BacktestAiInsight:
    symbol: str
    side: str  # long | scalp
    action: str = "keep"
    prefer_side: str = "neutral"
    confidence: int = 0
    reason_ko: str = ""
    applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "action": self.action,
            "prefer_side": self.prefer_side,
            "confidence": self.confidence,
            "reason_ko": self.reason_ko,
            "applied": self.applied,
        }


def _ai_enabled(config: AppConfig | None) -> bool:
    if config is None or not getattr(config, "backtest_ai_enabled", False):
        return False
    return bool(_gemini_api_key(config))


def _max_calls(config: AppConfig | None) -> int:
    if config is None:
        return 5
    return int(getattr(config, "backtest_ai_max_symbols_per_batch", 5) or 5)


def _parse_ai_json(text: str) -> BacktestAiInsight | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    action = str(data.get("action") or "keep").lower()
    if action not in VALID_ACTIONS:
        action = "keep"
    prefer = str(data.get("prefer_side") or "neutral").lower()
    if prefer == "short":
        prefer = "scalp"
    if prefer not in VALID_SIDES:
        prefer = "neutral"
    try:
        confidence = int(float(data.get("confidence") or 0))
    except (TypeError, ValueError):
        confidence = 0
    confidence = max(0, min(100, confidence))
    reason = str(data.get("reason_ko") or data.get("reason") or "").strip()[:160]
    return BacktestAiInsight(
        symbol="",
        side="long",
        action=action,
        prefer_side=prefer,
        confidence=confidence,
        reason_ko=reason,
    )


def _ticker_regime(
    symbol: str, tickers: dict[str, dict[str, Any]] | None
) -> tuple[float, float]:
    if not tickers:
        return 0.0, 0.0
    t = tickers.get(symbol.upper()) or {}
    chg = as_float(t.get("priceChangePercent"))
    vol = as_float(t.get("quoteVolume") or t.get("volume"))
    return round(chg, 2), round(vol, 0)


def _side_rank(st: SideStats) -> float:
    if st.trades < 1:
        return -999.0
    wr = as_float(st.win_rate_pct) / 100.0
    sl = max(0.1, as_float(st.best_sl_pct))
    tp = max(0.1, as_float(st.best_tp_pct))
    exp = wr * tp - (1 - wr) * sl
    return exp + as_float(st.score) * 0.15


def _best_side_for_symbol(rec: SymbolBacktestRecord) -> tuple[str, SideStats]:
    long_r = _side_rank(rec.long)
    short_r = _side_rank(rec.short)
    if short_r > long_r + 0.5:
        return "scalp", rec.short
    return "long", rec.long


def build_symbol_summary(
    sym: str,
    rec: SymbolBacktestRecord,
    *,
    tickers: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    side_label, st = _best_side_for_symbol(rec)
    chg, vol = _ticker_regime(sym, tickers)
    regime = "횡보"
    if chg > 2:
        regime = "상승"
    elif chg < -2:
        regime = "하락"
    return {
        "symbol": sym,
        "side": side_label,
        "trades": st.trades,
        "win_rate_pct": round(as_float(st.win_rate_pct), 1),
        "avg_return_pct": round(as_float(st.avg_return_pct), 3),
        "score": round(as_float(st.score), 1),
        "best_sl_pct": as_float(st.best_sl_pct),
        "best_tp_pct": as_float(st.best_tp_pct),
        "change_24h_pct": chg,
        "quote_volume": vol,
        "regime_24h": regime,
        "long_score": round(as_float(rec.long.score), 1),
        "scalp_score": round(as_float(rec.short.score), 1),
    }


def pick_symbols_for_ai(
    acc: BacktestAccumulator,
    batch_symbols: list[str],
    *,
    limit: int = 5,
) -> list[str]:
    """배치 내 상·하위 성과 종목 우선 (최대 limit)."""
    scored: list[tuple[float, str]] = []
    for sym in batch_symbols:
        rec = acc.symbols.get(sym.upper())
        if not rec:
            continue
        _, st = _best_side_for_symbol(rec)
        if st.trades < 1:
            continue
        scored.append((_side_rank(st), sym.upper()))
    if not scored:
        return []
    scored.sort(key=lambda x: x[0], reverse=True)
    picks: list[str] = []
    for _, sym in scored[: max(1, limit // 2)]:
        if sym not in picks:
            picks.append(sym)
    for _, sym in reversed(scored[-max(1, limit // 2) :]):
        if sym not in picks:
            picks.append(sym)
    for _, sym in scored:
        if len(picks) >= limit:
            break
        if sym not in picks:
            picks.append(sym)
    return picks[:limit]


def _user_prompt(summary: dict[str, Any]) -> str:
    return (
        "종목 백테스트 요약:\n"
        f"- 심볼: {summary['symbol']}\n"
        f"- 분석 방향: {summary['side']} (long=스윙·롱, scalp=단타·숏)\n"
        f"- 거래 수: {summary['trades']}, 승률: {summary['win_rate_pct']}%\n"
        f"- 평균 수익률: {summary['avg_return_pct']}%, BT점수: {summary['score']}\n"
        f"- 최적 손절/익절: {summary['best_sl_pct']}% / {summary['best_tp_pct']}%\n"
        f"- 24h 변동: {summary['change_24h_pct']}%, 거래대금(근사): {summary['quote_volume']}\n"
        f"- 시장 국면: {summary['regime_24h']}\n"
        f"- 롱 점수: {summary['long_score']}, 단타 점수: {summary['scalp_score']}\n"
        "권장: keep(유지), widen_tp(익절 확대), tighten_sl(손절 축소), "
        "block(종목 차단), boost(가중 상향), prefer_scalp/prefer_long(방향 선호)"
    )


async def _call_gemini(
    client: httpx.AsyncClient,
    api_key: str,
    summary: dict[str, Any],
) -> BacktestAiInsight | None:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )
    resp = await client.post(
        url,
        json={
            "contents": [
                {
                    "parts": [
                        {"text": f"{SYSTEM_PROMPT}\n\n{_user_prompt(summary)}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        },
        timeout=22.0,
    )
    resp.raise_for_status()
    parts = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = parts[0].get("text", "") if parts else ""
    parsed = _parse_ai_json(text)
    if not parsed:
        return None
    parsed.symbol = str(summary["symbol"]).upper()
    parsed.side = str(summary["side"])
    return parsed


async def fetch_ai_insights_for_batch(
    config: AppConfig,
    acc: BacktestAccumulator,
    batch_symbols: list[str],
    *,
    tickers: dict[str, dict[str, Any]] | None = None,
) -> list[BacktestAiInsight]:
    if not _ai_enabled(config):
        return []
    api_key = _gemini_api_key(config)
    symbols = pick_symbols_for_ai(acc, batch_symbols, limit=_max_calls(config))
    if not symbols or not api_key:
        return []

    insights: list[BacktestAiInsight] = []
    headers = {"User-Agent": "AIDI/1.0 (backtest-ai)"}
    async with httpx.AsyncClient(timeout=24.0, headers=headers, trust_env=True) as client:
        for sym in symbols:
            rec = acc.symbols.get(sym)
            if not rec:
                continue
            summary = build_symbol_summary(sym, rec, tickers=tickers)
            try:
                ins = await _call_gemini(client, api_key, summary)
            except Exception as exc:
                logger.debug("[백테스트 AI] Gemini 실패 %s: %s", sym, exc)
                continue
            if ins:
                insights.append(ins)
    return insights


def _apply_single_insight(
    learning: BacktestLearningState,
    acc: BacktestAccumulator,
    ins: BacktestAiInsight,
) -> bool:
    """규칙 학습과 병합 — 한 건 적용 여부."""
    sym = ins.symbol.upper()
    rec = acc.symbols.get(sym)
    if not rec:
        return False
    conf = ins.confidence
    applied = False
    side_key = "short" if ins.side == "scalp" else "long"
    st = rec.short if side_key == "short" else rec.long

    if ins.action == "block" and conf >= 65:
        blocked = set(learning.blocked_symbols)
        blocked.add(sym)
        learning.blocked_symbols = sorted(blocked)[-80:]
        applied = True
    elif ins.action == "boost" and conf >= 60:
        learning.blocked_symbols = [s for s in learning.blocked_symbols if s != sym]
        if st.trades >= 1 and as_float(st.score) > 0:
            st.score = min(100.0, as_float(st.score) + min(4.0, conf * 0.04))
            applied = True
    elif ins.action == "widen_tp" and conf >= 55 and as_float(st.best_tp_pct) > 0:
        mode = "scalp" if ins.side == "scalp" else "long"
        sl, tp = _clamp_auto_sl_tp(
            mode,
            as_float(st.best_sl_pct),
            as_float(st.best_tp_pct) * 1.06,
        )
        st.best_tp_pct = tp
        st.best_sl_pct = sl
        applied = True
    elif ins.action == "tighten_sl" and conf >= 55 and as_float(st.best_sl_pct) > 0:
        mode = "scalp" if ins.side == "scalp" else "long"
        sl, tp = _clamp_auto_sl_tp(
            mode,
            as_float(st.best_sl_pct) * 0.94,
            as_float(st.best_tp_pct),
        )
        st.best_sl_pct = sl
        st.best_tp_pct = tp
        applied = True
    elif ins.action == "prefer_scalp" and conf >= 58:
        learning.scalp_min_bt_score = max(30.0, learning.scalp_min_bt_score - 0.3)
        applied = True
    elif ins.action == "prefer_long" and conf >= 58:
        learning.long_min_bt_score = max(34.0, learning.long_min_bt_score - 0.3)
        applied = True

    ins.applied = applied
    return applied


def merge_ai_insights_into_learning(
    learning: BacktestLearningState,
    acc: BacktestAccumulator,
    insights: list[BacktestAiInsight],
) -> BacktestLearningState:
    if not insights:
        return learning
    applied_n = 0
    lines: list[str] = []
    for ins in insights:
        if _apply_single_insight(learning, acc, ins):
            applied_n += 1
        tag = "적용" if ins.applied else "참고"
        lines.append(
            f"{ins.symbol.replace('USDT', '')}({ins.side}) "
            f"{ins.action} {ins.confidence}% {tag}: {ins.reason_ko[:50]}"
        )
        logger.info(
            "[백테스트 AI] %s %s %s conf=%d %s — %s",
            ins.symbol,
            ins.side,
            ins.action,
            ins.confidence,
            "적용" if ins.applied else "미적용",
            ins.reason_ko[:80],
        )
    learning.ai_recent_insights = [i.to_dict() for i in insights][-20:]
    if lines:
        learning.last_ai_message = " · ".join(lines[:4])
        if applied_n:
            prev = learning.last_adjust_message or ""
            learning.last_adjust_message = (
                f"{prev} · AI {applied_n}건 반영".strip(" · ")
                if prev
                else f"AI {applied_n}건 반영"
            )
    acc.save()
    learning.updated_at = time.time()
    save_learning_state(learning)
    return learning


async def apply_ai_backtest_insights(
    config: AppConfig | None,
    acc: BacktestAccumulator,
    batch_symbols: list[str],
    *,
    tickers: dict[str, dict[str, Any]] | None = None,
) -> list[BacktestAiInsight]:
    """배치 종료 후 Gemini 제안 수집·규칙 학습과 병합."""
    if not _ai_enabled(config):
        return []
    insights = await fetch_ai_insights_for_batch(
        config, acc, batch_symbols, tickers=tickers
    )
    if not insights:
        return []
    learning = load_learning_state()
    merge_ai_insights_into_learning(learning, acc, insights)
    return insights

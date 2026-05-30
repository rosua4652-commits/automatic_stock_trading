"""차트·추세 분석 후 진입 적합 여부 판단."""

from dataclasses import dataclass

import numpy as np

from app.market.binance import binance


@dataclass
class EntrySignal:
    ok: bool
    score: float
    outlook: str
    pattern: str
    reasons: list[str]
    rsi: float
    trend: str


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    if len(values) < period:
        return values
    alpha = 2 / (period + 1)
    out = np.empty_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def _rsi(closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes[-(period + 1) :])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains.mean() or 1e-9
    avg_loss = losses.mean() or 1e-9
    return float(100 - (100 / (1 + avg_gain / avg_loss)))


def _analyze_closes(closes: np.ndarray, volumes: np.ndarray) -> tuple[float, str, str, list[str], float, str]:
    reasons: list[str] = []
    score = 0.0

    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    ema50 = _ema(closes, 50)
    rsi = _rsi(closes)

    # 추세: 정배열 + 가격이 단기 이평 위
    if closes[-1] > ema12[-1] > ema26[-1] > ema50[-1]:
        score += 28
        trend = "강한 상승"
        reasons.append("이평 정배열")
    elif closes[-1] > ema26[-1] and ema12[-1] > ema50[-1]:
        score += 18
        trend = "상승"
        reasons.append("상승 추세")
    elif closes[-1] < ema26[-1] and ema12[-1] < ema50[-1]:
        score -= 8
        trend = "하락"
        reasons.append("약한 하락")
    else:
        trend = "횡보"
        score += 12
        reasons.append("횡보·단타 가능")

    # RSI: 과열/과매도
    if 42 <= rsi <= 62:
        score += 22
        reasons.append(f"RSI {rsi:.0f} 적정")
    elif rsi > 78:
        score -= 12
        reasons.append(f"RSI {rsi:.0f} 과열")
    elif rsi < 32:
        score += 8
        reasons.append("과매도 구간")
    else:
        score += 5

    # 최근 5봉 고저: higher lows
    if len(closes) >= 6:
        lows = [min(closes[i - 1], closes[i]) for i in range(-5, 0)]
        if all(lows[i] <= lows[i + 1] for i in range(len(lows) - 1)):
            score += 15
            reasons.append("저점 상승")
        highs = [max(closes[i - 1], closes[i]) for i in range(-5, 0)]
        if highs[-1] < highs[-2] < highs[-3]:
            score -= 12
            reasons.append("고점 하락")

    # 거래량: 최근 상승봉에 거래량 동반
    if len(volumes) >= 10:
        up_vol = volumes[-5:][closes[-5:] > np.roll(closes, 1)[-5:]].mean() if len(volumes) >= 6 else 0
        avg_vol = volumes[-20:-5].mean() + 1e-9
        if up_vol > avg_vol * 1.05:
            score += 12
            reasons.append("거래량 동반")

    # 긴 윗꼬리(매도 압력) 최근 봉
    if len(closes) >= 3:
        for i in range(-3, 0):
            o, c, h, l = closes[i - 1], closes[i], closes[i] * 1.002, closes[i] * 0.998
            body = abs(c - o) + 1e-9
            upper_wick = h - max(o, c)
            if upper_wick / body > 2.5 and c < o:
                score -= 10
                reasons.append("윗꼬리 매도압")
                break

    # 24봉 모멘텀
    if len(closes) >= 24:
        mom = (closes[-1] - closes[-24]) / closes[-24] * 100
        if mom > 3:
            score += 10
            reasons.append("모멘텀 양호")
        elif mom < -8:
            score -= 8
            reasons.append("모멘텀 약세")

    if score >= 58:
        outlook = "단타·상승 우세"
        pattern = "돌파·추세형"
    elif score >= 38:
        outlook = "단타 관망·진입 가능"
        pattern = "횡보·스캘핑"
    else:
        outlook = "진입 부적합"
        pattern = "약세·하락"

    return score, outlook, pattern, reasons, rsi, trend


async def analyze_entry(symbol: str, min_score: float = 45.0) -> EntrySignal:
    """15m·1h 차트 — 단타·빠른 진입·청산용 (기준 완화)."""
    try:
        raw_15m = await binance.klines(symbol, "15m", 120)
        raw_1h = await binance.klines(symbol, "1h", 80)
    except Exception:
        return EntrySignal(
            ok=False,
            score=0,
            outlook="데이터 부족",
            pattern="-",
            reasons=["차트 로드 실패"],
            rsi=50,
            trend="-",
        )

    if len(raw_15m) < 40:
        return EntrySignal(
            ok=False, score=0, outlook="데이터 부족", pattern="-",
            reasons=["캔들 부족"], rsi=50, trend="-",
        )

    c15 = np.array([float(r[4]) for r in raw_15m], dtype=float)
    v15 = np.array([float(r[5]) for r in raw_15m], dtype=float)
    s15, o15, p15, r15, rsi15, t15 = _analyze_closes(c15, v15)

    s1h, o1h, p1h, r1h, rsi1h, t1h = s15, o15, p15, r15, rsi15, t15
    if len(raw_1h) >= 40:
        c1h = np.array([float(r[4]) for r in raw_1h], dtype=float)
        v1h = np.array([float(r[5]) for r in raw_1h], dtype=float)
        s1h, o1h, p1h, r1h, rsi1h, t1h = _analyze_closes(c1h, v1h)

    combined = s15 * 0.65 + s1h * 0.35
    reasons = list(dict.fromkeys(r15 + r1h))[:8]
    outlook = o15 if s15 >= s1h else o1h
    pattern = p15 if s15 >= s1h else p1h
    trend = t15 if s15 >= s1h else t1h
    rsi = (rsi15 + rsi1h) / 2

    # 단타: 점수·횡보·약반등 허용, 극과열·깊은 하락만 제외
    ok = combined >= min_score and rsi < 82
    if trend == "하락" and combined < min_score + 5:
        ok = False

    return EntrySignal(
        ok=ok,
        score=round(combined, 1),
        outlook=outlook,
        pattern=pattern,
        reasons=reasons,
        rsi=round(rsi, 1),
        trend=trend,
    )


def format_entry_detail(
    signal: EntrySignal,
    *,
    min_entry_score: float,
    min_market_score: float = 0,
    market_score: float = 0,
) -> str:
    """진입 가능/불가 사유를 사용자용 문장으로."""
    if signal.outlook == "데이터 부족":
        return "차트 데이터 부족 — " + ", ".join(signal.reasons)

    blockers: list[str] = []
    if market_score > 0 and market_score < min_market_score:
        blockers.append(
            f"시장 점수 {market_score:.0f}점 (기준 {min_market_score:.0f}점 미만)"
        )
    if signal.score < min_entry_score:
        blockers.append(
            f"차트 점수 {signal.score:.0f}점 (기준 {min_entry_score:.0f}점 미만)"
        )
    if signal.trend == "하락" and signal.score < min_entry_score + 5:
        blockers.append(f"추세 '{signal.trend}' — 단타 기준 미달")
    if signal.rsi >= 82:
        blockers.append(f"RSI {signal.rsi:.0f} — 극과열(82 이상)")
    if signal.outlook == "진입 부적합":
        blockers.append(f"차트 전망 '{signal.outlook}' ({signal.pattern})")

    if signal.ok:
        pos = ", ".join(signal.reasons[:5]) if signal.reasons else signal.outlook
        return f"✓ 단타 진입 가능 — {signal.outlook} · {pos}"

    if signal.score >= min_entry_score - 8:
        head = "진입 보류 (근접)"
    else:
        head = "진입 보류"
    if blockers:
        head = "진입 불가 — " + " / ".join(blockers)
    elif not signal.ok:
        head = "진입 불가 — 종합 조건 미달"

    chart_notes = ", ".join(signal.reasons[:6]) if signal.reasons else signal.pattern
    return f"{head} | 차트 분석: {chart_notes}"

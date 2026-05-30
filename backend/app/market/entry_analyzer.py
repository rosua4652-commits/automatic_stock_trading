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
        score -= 20
        trend = "하락"
        reasons.append("하락 추세")
    else:
        trend = "횡보"
        score += 5

    # RSI: 과열/과매도
    if 42 <= rsi <= 62:
        score += 22
        reasons.append(f"RSI {rsi:.0f} 적정")
    elif rsi > 72:
        score -= 25
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
        elif mom < -5:
            score -= 15
            reasons.append("모멘텀 약세")

    if score >= 65:
        outlook = "상승 가능성 높음"
        pattern = "돌파·추세형"
    elif score >= 45:
        outlook = "관망·약한 상승"
        pattern = "횡보·조정"
    else:
        outlook = "진입 부적합"
        pattern = "약세·하락"

    return score, outlook, pattern, reasons, rsi, trend


async def analyze_entry(symbol: str, min_score: float = 60.0) -> EntrySignal:
    """1h·4h 차트 종합 — 올라갈 그래프 패턴인지 판단."""
    try:
        raw_1h = await binance.klines(symbol, "1h", 120)
        raw_4h = await binance.klines(symbol, "4h", 80)
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

    if len(raw_1h) < 50:
        return EntrySignal(
            ok=False, score=0, outlook="데이터 부족", pattern="-",
            reasons=["캔들 부족"], rsi=50, trend="-",
        )

    c1 = np.array([float(r[4]) for r in raw_1h], dtype=float)
    v1 = np.array([float(r[5]) for r in raw_1h], dtype=float)
    s1, o1, p1, r1, rsi1, t1 = _analyze_closes(c1, v1)

    s2, o2, p2, r2, rsi2, t2 = 0.0, o1, p1, [], rsi1, t1
    if len(raw_4h) >= 40:
        c4 = np.array([float(r[4]) for r in raw_4h], dtype=float)
        v4 = np.array([float(r[5]) for r in raw_4h], dtype=float)
        s2, o2, p2, r2, rsi2, t2 = _analyze_closes(c4, v4)

    combined = s1 * 0.6 + s2 * 0.4
    reasons = list(dict.fromkeys(r1 + r2))[:8]
    outlook = o1 if combined >= 55 else o2
    pattern = p1 if s1 >= s2 else p2
    trend = t1 if s1 >= s2 else t2
    rsi = (rsi1 + rsi2) / 2

    ok = combined >= min_score and "하락" not in trend and rsi < 75

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
    if "하락" in signal.trend:
        blockers.append(f"추세 '{signal.trend}' — 하락 구간은 자동 진입 안 함")
    if signal.rsi >= 75:
        blockers.append(f"RSI {signal.rsi:.0f} — 과열(75 이상) 구간")
    if signal.outlook == "진입 부적합":
        blockers.append(f"차트 전망 '{signal.outlook}' ({signal.pattern})")

    if signal.ok:
        pos = ", ".join(signal.reasons[:5]) if signal.reasons else signal.outlook
        return f"✓ 자동 진입 가능 — {signal.outlook} · {pos}"

    head = "진입 보류"
    if blockers:
        head = "진입 불가 — " + " / ".join(blockers)
    elif not signal.ok:
        head = "진입 불가 — 종합 조건 미달"

    chart_notes = ", ".join(signal.reasons[:6]) if signal.reasons else signal.pattern
    return f"{head} | 차트 분석: {chart_notes}"

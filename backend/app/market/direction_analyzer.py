"""롱/숏 방향 분석 — 일목·이평·볼린저·RSI."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.market.entry_analyzer import _ema, _rsi
from app.market.upbit_data import market


@dataclass
class DirectionSignalResult:
    ok: bool
    score: float
    side: str
    outlook: str
    detail: str
    reasons: list[str]
    rsi: float
    trend: str
    price_usdt: float = 0.0


def _bollinger(closes: np.ndarray, period: int = 20, mult: float = 2.0):
    if len(closes) < period:
        return 0.0, 0.0, 0.0
    mid = closes[-period:].mean()
    std = closes[-period:].std() or 1e-9
    return float(mid - mult * std), float(mid), float(mid + mult * std)


def _ichimoku(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray):
    """전환·기준·선행스팬 A/B (26봉 선행은 판정에서 제외)."""
    n = len(closes)
    if n < 52:
        return None

    def mid(h, l, p):
        if len(h) < p:
            return 0.0
        return float((h[-p:].max() + l[-p:].min()) / 2)

    tenkan = mid(highs, lows, 9)
    kijun = mid(highs, lows, 26)
    span_a = (tenkan + kijun) / 2
    span_b = mid(highs, lows, 52)
    return tenkan, kijun, span_a, span_b


def _analyze_long(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    volumes: np.ndarray,
) -> tuple[float, list[str], str, float, str]:
    reasons: list[str] = []
    score = 0.0
    price = float(closes[-1])
    rsi = _rsi(closes)

    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, min(200, len(closes)))

    bb_low, bb_mid, bb_high = _bollinger(closes)
    ichi = _ichimoku(highs, lows, closes)

    if ichi:
        tenkan, kijun, span_a, span_b = ichi
        cloud_top = max(span_a, span_b)
        cloud_bot = min(span_a, span_b)
        if price > cloud_top:
            score += 22
            reasons.append("일목 구름 위(강세)")
        elif price > cloud_bot:
            score += 10
            reasons.append("일목 구름 안·상단")
        else:
            score -= 15
            reasons.append("일목 구름 아래")
        if tenkan > kijun:
            score += 14
            reasons.append("전환>기준")
        else:
            score -= 8
            reasons.append("전환<기준")

    if price > ema20[-1] > ema50[-1]:
        score += 18
        reasons.append("EMA20>50 정배열")
    elif price > ema20[-1]:
        score += 8
        reasons.append("단기 이평 위")
    else:
        score -= 6

    if len(ema200) > 10 and price > ema200[-1]:
        score += 6
        reasons.append("장기 이평 위")

    if 38 <= rsi <= 62:
        score += 16
        reasons.append(f"RSI {rsi:.0f} 롱 적정")
    elif rsi < 35:
        score += 10
        reasons.append(f"RSI {rsi:.0f} 과매도 반등")
    elif rsi > 72:
        score -= 12
        reasons.append(f"RSI {rsi:.0f} 과열")

    if bb_low > 0 and price <= bb_low * 1.01:
        score += 12
        reasons.append("볼린저 하단 터치")
    elif bb_mid > 0 and bb_low < price < bb_mid:
        score += 8
        reasons.append("볼린저 중하단")
    elif price > bb_high * 0.998:
        score -= 10
        reasons.append("볼린저 상단")

    if len(volumes) >= 10:
        v5 = volumes[-5:].mean()
        v20 = volumes[-20:-5].mean() + 1e-9
        if v5 > v20 * 1.08 and closes[-1] > closes[-5]:
            score += 8
            reasons.append("거래량 동반 상승")

    if len(closes) >= 12:
        mom = (closes[-1] - closes[-12]) / closes[-12] * 100
        if mom > 2:
            score += 6
            reasons.append(f"12봉 +{mom:.1f}%")

    trend = "상승" if score >= 45 else "횡보" if score >= 28 else "약세"
    outlook = "롱 진입 검토" if score >= 52 else "롱 약함"
    return score, reasons, outlook, rsi, trend


def _analyze_short(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    volumes: np.ndarray,
) -> tuple[float, list[str], str, float, str]:
    reasons: list[str] = []
    score = 0.0
    price = float(closes[-1])
    rsi = _rsi(closes)

    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    bb_low, bb_mid, bb_high = _bollinger(closes)
    ichi = _ichimoku(highs, lows, closes)

    if ichi:
        tenkan, kijun, span_a, span_b = ichi
        cloud_top = max(span_a, span_b)
        cloud_bot = min(span_a, span_b)
        if price < cloud_bot:
            score += 22
            reasons.append("일목 구름 아래(약세)")
        elif price < cloud_top:
            score += 8
            reasons.append("구름 하단")
        else:
            score -= 15
            reasons.append("구름 위")
        if tenkan < kijun:
            score += 14
            reasons.append("전환<기준")
        else:
            score -= 8

    if price < ema20[-1] < ema50[-1]:
        score += 18
        reasons.append("EMA 역배열")
    elif price < ema20[-1]:
        score += 8
        reasons.append("단기 이평 아래")

    if 38 <= rsi <= 62:
        score += 12
        reasons.append(f"RSI {rsi:.0f} 숏 적정")
    elif rsi > 68:
        score += 16
        reasons.append(f"RSI {rsi:.0f} 과열 숏")
    elif rsi < 28:
        score -= 10
        reasons.append("RSI 과매도")

    if bb_high > 0 and price >= bb_high * 0.99:
        score += 14
        reasons.append("볼린저 상단")
    elif bb_mid > 0 and price > bb_mid:
        score += 6
        reasons.append("볼린저 중상단")

    if len(volumes) >= 10 and closes[-1] < closes[-5]:
        v5 = volumes[-5:].mean()
        v20 = volumes[-20:-5].mean() + 1e-9
        if v5 > v20 * 1.05:
            score += 8
            reasons.append("거래량 동반 하락")

    if len(closes) >= 12:
        mom = (closes[-1] - closes[-12]) / closes[-12] * 100
        if mom < -2:
            score += 8
            reasons.append(f"12봉 {mom:.1f}%")

    trend = "하락" if score >= 45 else "횡보" if score >= 28 else "강세"
    outlook = "숏 진입 검토" if score >= 52 else "숏 약함"
    return score, reasons, outlook, rsi, trend


def _format_detail(side: str, score: float, reasons: list[str], rsi: float, trend: str) -> str:
    label = "롱" if side == "long" else "숏"
    body = " · ".join(reasons[:7]) if reasons else trend
    return f"{label} {score:.0f}점 · RSI {rsi:.0f} · {trend} · {body}"


async def analyze_direction(symbol: str, side: str, *, min_score: float = 50.0) -> DirectionSignalResult:
    side = side.lower()
    if side not in ("long", "short"):
        side = "long"

    try:
        raw = await market.klines(symbol, "15m", 120)
        raw1h = await market.klines(symbol, "1h", 80)
    except Exception as e:
        return DirectionSignalResult(
            ok=False,
            score=0,
            side=side,
            outlook="데이터 없음",
            detail=str(e)[:80],
            reasons=["차트 로드 실패"],
            rsi=50,
            trend="-",
        )

    if len(raw) < 50:
        return DirectionSignalResult(
            ok=False,
            score=0,
            side=side,
            outlook="캔들 부족",
            detail="분석할 봉 수가 부족합니다",
            reasons=[],
            rsi=50,
            trend="-",
        )

    def pack(rows):
        c = np.array([float(r[4]) for r in rows], dtype=float)
        h = np.array([float(r[2]) for r in rows], dtype=float)
        l = np.array([float(r[3]) for r in rows], dtype=float)
        v = np.array([float(r[5]) for r in rows], dtype=float)
        return c, h, l, v

    c15, h15, l15, v15 = pack(raw)
    if side == "long":
        s15, r15, o15, rsi15, t15 = _analyze_long(c15, h15, l15, v15)
    else:
        s15, r15, o15, rsi15, t15 = _analyze_short(c15, h15, l15, v15)

    s1h, r1h, o1h, rsi1h, t1h = s15, r15, o15, rsi15, t15
    if len(raw1h) >= 40:
        c1h, h1h, l1h, v1h = pack(raw1h)
        if side == "long":
            s1h, r1h, o1h, rsi1h, t1h = _analyze_long(c1h, h1h, l1h, v1h)
        else:
            s1h, r1h, o1h, rsi1h, t1h = _analyze_short(c1h, h1h, l1h, v1h)

    combined = s15 * 0.6 + s1h * 0.4
    reasons = list(dict.fromkeys(r15 + r1h))[:10]
    rsi = (rsi15 + rsi1h) / 2
    trend = t15 if s15 >= s1h else t1h
    outlook = o15 if s15 >= s1h else o1h
    price = float(c15[-1])

    ok = combined >= min_score
    detail = _format_detail(side, combined, reasons, rsi, trend)
    if not ok:
        detail = f"조건 미달 — {detail}"

    return DirectionSignalResult(
        ok=ok,
        score=round(combined, 1),
        side=side,
        outlook=outlook,
        detail=detail,
        reasons=reasons,
        rsi=round(rsi, 1),
        trend=trend,
        price_usdt=price,
    )

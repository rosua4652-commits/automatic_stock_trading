import time
from typing import Any

import numpy as np

from app.config import settings
from app.market.binance import binance
from app.models import CoinCandidate


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
    rs = avg_gain / avg_loss
    return float(100 - (100 / (1 + rs)))


def _score_symbol(closes: np.ndarray, volumes: np.ndarray, change_24h: float) -> tuple[float, str, float, str]:
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    rsi = _rsi(closes)
    vol_ratio = float(volumes[-24:].mean() / (volumes[-48:-24].mean() + 1e-9))

    trend = "상승" if ema20[-1] > ema50[-1] and closes[-1] > ema20[-1] else (
        "횡보" if abs(ema20[-1] - ema50[-1]) / ema50[-1] < 0.01 else "약세"
    )

    score = 0.0
    reasons: list[str] = []

    if trend == "상승":
        score += 35
        reasons.append("추세↑")
    elif trend == "횡보":
        score += 15
        reasons.append("횡보")
    else:
        score -= 10

    if 45 <= rsi <= 68:
        score += 25
        reasons.append("RSI적정")
    elif rsi < 35:
        score += 10
        reasons.append("과매도반등")
    elif rsi > 75:
        score -= 15
        reasons.append("과열")

    if change_24h > 0:
        score += min(change_24h, 8) * 2
    else:
        score += max(change_24h, -8)

    if vol_ratio > 1.1:
        score += 12
        reasons.append("거래량↑")

    momentum = (closes[-1] - closes[-24]) / closes[-24] * 100 if len(closes) >= 24 else 0
    if momentum > 2:
        score += 8
        reasons.append("모멘텀")

    reason = ", ".join(reasons) if reasons else "종합분석"
    return score, trend, rsi, reason


async def scan_market(limit: int = 12) -> list[CoinCandidate]:
    symbols_info, tickers = await binance.exchange_info(), await binance.tickers_24h()
    safe = [s for s in symbols_info if binance.is_safe_usdt_pair(s)]

    ranked: list[tuple[float, CoinCandidate]] = []

    # pre-filter by volume
    candidates: list[tuple[str, str, float, float]] = []
    for info in safe:
        symbol = info["symbol"]
        base = info["baseAsset"]
        t = tickers.get(symbol)
        if not t:
            continue
        quote_vol = float(t.get("quoteVolume", 0))
        if quote_vol < settings.min_quote_volume_usdt:
            continue
        change = float(t.get("priceChangePercent", 0))
        candidates.append((symbol, base, quote_vol, change))

    candidates.sort(key=lambda x: x[2], reverse=True)
    top_by_volume = candidates[:40]

    sem_tasks = []
    for symbol, base, quote_vol, change in top_by_volume:
        sem_tasks.append((symbol, base, quote_vol, change))

    for symbol, base, quote_vol, change in sem_tasks:
        try:
            raw = await binance.klines(symbol, "1h", settings.min_candles)
            if len(raw) < settings.min_candles:
                continue
            closes = np.array([float(r[4]) for r in raw], dtype=float)
            volumes = np.array([float(r[5]) for r in raw], dtype=float)
            # listing maturity proxy: need stable history without huge gaps
            if closes.std() / (closes.mean() + 1e-9) > 0.35:
                continue
            score, trend, rsi, reason = _score_symbol(closes, volumes, change)
            if score < 25:
                continue
            ranked.append(
                (
                    score,
                    CoinCandidate(
                        symbol=symbol,
                        base=base,
                        score=round(score, 1),
                        trend=trend,
                        rsi=round(rsi, 1),
                        change_24h=round(change, 2),
                        volume_usdt=quote_vol,
                        reason=reason,
                    ),
                )
            )
        except Exception:
            continue

    ranked.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in ranked[:limit]]

import asyncio
from collections.abc import Callable
from typing import Any

import numpy as np

from app.config import settings
from app.market.binance import binance
from app.market.coin_registry import coin_meta
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


def _score_symbol(
    closes: np.ndarray, volumes: np.ndarray, change_24h: float
) -> tuple[float, str, float, str]:
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    rsi = _rsi(closes)
    vol_ratio = float(volumes[-24:].mean() / (volumes[-48:-24].mean() + 1e-9))

    trend = (
        "상승"
        if ema20[-1] > ema50[-1] and closes[-1] > ema20[-1]
        else ("횡보" if abs(ema20[-1] - ema50[-1]) / ema50[-1] < 0.01 else "약세")
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


async def _analyze_one(
    symbol: str,
    base: str,
    quote_vol: float,
    change: float,
    is_running: Callable[[], bool],
) -> CoinCandidate | None:
    if not is_running():
        return None
    try:
        need = settings.scan_kline_min
        raw = await binance.klines(symbol, "1h", max(need, 80))
        if not is_running() or len(raw) < need:
            return None
        closes = np.array([float(r[4]) for r in raw], dtype=float)
        volumes = np.array([float(r[5]) for r in raw], dtype=float)
        if closes.std() / (closes.mean() + 1e-9) > 0.55:
            return None
        score, trend, rsi, reason = _score_symbol(closes, volumes, change)
        if score < 5:
            return None
        meta = coin_meta(symbol, base)
        return CoinCandidate(
            symbol=symbol,
            base=meta["base"],
            name_ko=meta["name_ko"],
            name_en=meta["name_en"],
            pair_label=meta["pair_label"],
            display=meta["display"],
            score=round(score, 1),
            trend=trend,
            rsi=round(rsi, 1),
            change_24h=round(change, 2),
            volume_usdt=quote_vol,
            reason=reason,
        )
    except Exception:
        return None


def _quick_score(change_24h: float, quote_vol: float) -> tuple[float, str, float, str]:
    score = 20.0
    if change_24h > 0:
        score += min(change_24h, 12) * 1.5
    else:
        score += max(change_24h, -10)
    if quote_vol > 50_000_000:
        score += 12
    elif quote_vol > 10_000_000:
        score += 6
    trend = "상승" if change_24h > 2 else ("하락" if change_24h < -2 else "횡보")
    rsi = 50.0
    return round(score, 1), trend, rsi, "거래대금·24h 기준"


async def build_ticker_candidates(
    symbols: list[str],
    tickers: dict[str, dict],
) -> list[CoinCandidate]:
    """캔들 분석 없이 탭·목록용 경량 후보."""
    out: list[CoinCandidate] = []
    for symbol in symbols:
        t = tickers.get(symbol)
        if not t:
            continue
        base = symbol.replace("USDT", "")
        quote_vol = float(t.get("quoteVolume", 0))
        change = float(t.get("priceChangePercent", 0))
        score, trend, rsi, reason = _quick_score(change, quote_vol)
        meta = coin_meta(symbol, base)
        out.append(
            CoinCandidate(
                symbol=symbol,
                base=meta["base"],
                name_ko=meta["name_ko"],
                name_en=meta["name_en"],
                pair_label=meta["pair_label"],
                display=meta["display"],
                score=score,
                trend=trend,
                rsi=rsi,
                change_24h=round(change, 2),
                volume_usdt=quote_vol,
                reason=reason,
            )
        )
    return out


async def top_usdt_symbols(
    limit: int | None = None,
    is_running: Callable[[], bool] | None = None,
) -> list[str]:
    """거래대금 상위 USDT 페어 (차트 분석 없이 탭·탐색용)."""
    running = is_running or (lambda: True)
    if not running():
        return []
    symbols_info, tickers = await binance.exchange_info(), await binance.tickers_24h()
    if not running():
        return []
    safe = [s for s in symbols_info if binance.is_safe_usdt_pair(s)]
    ranked: list[tuple[str, float]] = []
    for info in safe:
        symbol = info["symbol"]
        t = tickers.get(symbol)
        if not t:
            continue
        quote_vol = float(t.get("quoteVolume", 0))
        if quote_vol < settings.min_quote_volume_usdt:
            continue
        ranked.append((symbol, quote_vol))
    ranked.sort(key=lambda x: x[1], reverse=True)
    cap = limit if limit is not None else settings.tab_symbol_limit
    return [s for s, _ in ranked[:cap]]


async def scan_market(
    limit: int | None = None,
    is_running: Callable[[], bool] | None = None,
) -> list[CoinCandidate]:
    running = is_running or (lambda: True)
    if not running():
        return []

    symbols_info, tickers = await binance.exchange_info(), await binance.tickers_24h()
    if not running():
        return []

    safe = [s for s in symbols_info if binance.is_safe_usdt_pair(s)]
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
    scan_cap = limit if limit is not None else settings.scan_candidate_limit
    top = candidates[: max(scan_cap * 2, 200)]

    sem = asyncio.Semaphore(16)

    async def run_one(item: tuple[str, str, float, float]) -> CoinCandidate | None:
        if not running():
            return None
        async with sem:
            return await _analyze_one(*item, is_running=running)

    results = await asyncio.gather(*[run_one(c) for c in top])
    ranked = [(c.score, c) for c in results if c is not None]
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in ranked[:scan_cap]]

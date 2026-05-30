"""업비트 매도 — 시장가 5,000원 미만이면 지정가(최소 주문금액 충족)로 전환."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from app.market.upbit_client import UpbitClient

# 업비트 시장가 매도: 수량 × 매수1호가 >= 5,000원 (under_min_total_market_ask)
MIN_MARKET_ASK_KRW = float(getattr(settings, "min_market_ask_krw", 5_000.0))


def price_tick_krw(price: float) -> float:
    """업비트 KRW 마켓 호가 단위."""
    p = max(float(price), 1e-12)
    if p >= 2_000_000:
        return 1000.0
    if p >= 1_000_000:
        return 500.0
    if p >= 500_000:
        return 100.0
    if p >= 100_000:
        return 50.0
    if p >= 10_000:
        return 10.0
    if p >= 1_000:
        return 5.0
    if p >= 100:
        return 1.0
    if p >= 10:
        return 0.1
    if p >= 1:
        return 0.01
    if p >= 0.1:
        return 0.001
    return 0.0001


def ceil_to_tick(price: float, tick: float) -> float:
    t = max(tick, 1e-12)
    return math.ceil(price / t - 1e-12) * t


def format_upbit_price(price_krw: float) -> str:
    tick = price_tick_krw(price_krw)
    rounded = ceil_to_tick(max(price_krw, tick), tick)
    if tick >= 1:
        return str(int(round(rounded)))
    decimals = max(0, int(round(-math.log10(tick))))
    return f"{rounded:.{decimals}f}".rstrip("0").rstrip(".")


def min_limit_price_krw(volume: float, *, floor_bid: float = 0.0) -> float:
    """주문 금액이 최소 5,000원이 되도록 하는 지정가(매도)."""
    vol = max(float(volume), 1e-12)
    need = MIN_MARKET_ASK_KRW / vol
    base = max(float(floor_bid), need)
    tick = price_tick_krw(base)
    return ceil_to_tick(base, tick)


def is_under_min_market_ask_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "under_min_total_market_ask" in text


async def fetch_best_bid_krw(client: "UpbitClient", market: str) -> float:
    http = await client._ensure()
    resp = await http.get("/v1/orderbook", params={"markets": market})
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        return 0.0
    units = rows[0].get("orderbook_units") or []
    if not units:
        return 0.0
    return float(units[0].get("bid_price") or 0)


async def smart_sell(
    client: "UpbitClient",
    market: str,
    volume: float,
    *,
    bid_hint_krw: float = 0.0,
) -> tuple[dict, str]:
    """
    시장가 매도 시도 → 5천원 미만이면 지정가(IOC) 전량 매도.
    반환: (order, mode_label)
    """
    vol = max(float(volume), 0.0)
    if vol <= 0:
        raise RuntimeError("매도 수량 없음")

    bid = bid_hint_krw if bid_hint_krw > 0 else await fetch_best_bid_krw(client, market)
    notional = vol * bid if bid > 0 else 0.0

    if notional >= MIN_MARKET_ASK_KRW - 0.5:
        try:
            return await client.market_sell(market, vol), "시장가"
        except RuntimeError as e:
            if not is_under_min_market_ask_error(e):
                raise

    limit_px = min_limit_price_krw(vol, floor_bid=bid)
    try:
        order = await client.limit_sell(
            market, vol, limit_px, time_in_force="ioc"
        )
        return order, f"지정가 {format_upbit_price(limit_px)}원 (5천원 미만·IOC)"
    except RuntimeError:
        order = await client.limit_sell(market, vol, limit_px, time_in_force="gtc")
        return order, f"지정가 {format_upbit_price(limit_px)}원 (5천원 미만)"

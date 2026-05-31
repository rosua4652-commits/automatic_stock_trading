"""업비트 매도 — 5,000원 미만 소액: 지정가 대기 + 시장가 가능 시 자동 재시도."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.config import settings

if TYPE_CHECKING:
    from app.market.upbit_client import UpbitClient

# 업비트 시장가 매도: 수량 × 매수1호가 >= 5,000원
MIN_MARKET_ASK_KRW = float(getattr(settings, "min_market_ask_krw", 5_000.0))


@dataclass
class SellOutcome:
    order: dict[str, Any]
    mode: str
    filled: bool
    pending: bool = False
    min_bid_for_market: float = 0.0
    limit_price_krw: float = 0.0


def price_tick_krw(price: float) -> float:
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
    vol = max(float(volume), 1e-12)
    need = MIN_MARKET_ASK_KRW / vol
    base = max(float(floor_bid), need)
    tick = price_tick_krw(base)
    return ceil_to_tick(base, tick)


def min_bid_for_market_sell(volume: float) -> float:
    vol = max(float(volume), 1e-12)
    return MIN_MARKET_ASK_KRW / vol


def is_under_min_market_ask_error(exc: BaseException) -> bool:
    return "under_min_total_market_ask" in str(exc).lower()


def order_executed_qty(order: dict[str, Any]) -> float:
    try:
        return float(order.get("executed_volume") or 0)
    except (TypeError, ValueError):
        return 0.0


def order_is_open(order: dict[str, Any]) -> bool:
    return str(order.get("state") or "") in ("wait", "watch")


async def fetch_orderbook_top(
    client: "UpbitClient", market: str
) -> tuple[float, float]:
    """(best_bid, best_ask) KRW."""
    http = await client._ensure()
    resp = await http.get("/v1/orderbook", params={"markets": market})
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        return 0.0, 0.0
    units = rows[0].get("orderbook_units") or []
    if not units:
        return 0.0, 0.0
    u0 = units[0]
    return float(u0.get("bid_price") or 0), float(u0.get("ask_price") or 0)


async def _try_market_sell(
    client: "UpbitClient", market: str, volume: float
) -> SellOutcome | None:
    try:
        order = await client.market_sell(market, volume)
        qty = order_executed_qty(order)
        return SellOutcome(
            order=order,
            mode="시장가",
            filled=qty > volume * 1e-6,
        )
    except RuntimeError as e:
        if is_under_min_market_ask_error(e):
            return None
        raise


async def _try_limit_ioc(
    client: "UpbitClient",
    market: str,
    volume: float,
    price_krw: float,
    label: str,
) -> SellOutcome | None:
    try:
        order = await client.limit_sell(
            market, volume, price_krw, time_in_force="ioc"
        )
        qty = order_executed_qty(order)
        if qty > volume * 1e-6:
            return SellOutcome(order=order, mode=label, filled=True)
    except RuntimeError:
        pass
    return None


async def smart_sell(
    client: "UpbitClient",
    market: str,
    volume: float,
    *,
    bid_hint_krw: float = 0.0,
    cancel_existing_asks: bool = True,
) -> SellOutcome:
    vol = max(float(volume), 0.0)
    if vol <= 0:
        raise RuntimeError("매도 수량 없음")

    if cancel_existing_asks:
        await client.cancel_open_orders(market, side="ask")

    bid, ask = await fetch_orderbook_top(client, market)
    if bid_hint_krw > 0 and bid <= 0:
        bid = bid_hint_krw
    if bid_hint_krw > 0 and ask <= 0:
        ask = bid_hint_krw

    min_bid = min_bid_for_market_sell(vol)

    if bid > 0 and vol * bid >= MIN_MARKET_ASK_KRW - 0.5:
        got = await _try_market_sell(client, market, vol)
        if got and got.filled:
            return got

    if ask > 0 and vol * ask >= MIN_MARKET_ASK_KRW - 0.5:
        px = ceil_to_tick(ask, price_tick_krw(ask))
        label = f"지정가 {format_upbit_price(px)}원 (매도호가·IOC)"
        got = await _try_limit_ioc(client, market, vol, px, label)
        if got:
            return got

    try:
        order = await client.best_sell(market, vol)
        qty = order_executed_qty(order)
        if qty > vol * 1e-6:
            return SellOutcome(order=order, mode="최유리", filled=True)
    except RuntimeError as e:
        if not is_under_min_market_ask_error(e):
            pass

    limit_px = min_limit_price_krw(vol, floor_bid=bid)
    got = await _try_limit_ioc(
        client,
        market,
        vol,
        limit_px,
        f"지정가 {format_upbit_price(limit_px)}원 (최소금액·IOC)",
    )
    if got:
        return got

    order = await client.limit_sell(market, vol, limit_px, time_in_force="gtc")
    qty = order_executed_qty(order)
    mode = f"지정가 {format_upbit_price(limit_px)}원 (소액·대기)"
    if qty > vol * 1e-6:
        return SellOutcome(order=order, mode=mode, filled=True)
    if order_is_open(order):
        return SellOutcome(
            order=order,
            mode=mode,
            filled=False,
            pending=True,
            min_bid_for_market=min_bid,
            limit_price_krw=limit_px,
        )
    return SellOutcome(
        order=order,
        mode=mode,
        filled=False,
        pending=True,
        min_bid_for_market=min_bid,
        limit_price_krw=limit_px,
    )


def set_pending_exit(
    live_meta: dict,
    symbol: str,
    *,
    reason: str,
    min_bid_krw: float,
    limit_price_krw: float,
    order_uuid: str = "",
) -> None:
    sym = symbol.upper()
    live_meta.setdefault("positions_meta", {}).setdefault(sym, {})[
        "pending_exit"
    ] = {
        "reason": reason,
        "min_bid_krw": round(min_bid_krw, 4),
        "limit_price_krw": round(limit_price_krw, 4),
        "order_uuid": str(order_uuid or ""),
    }


def clear_pending_exit(live_meta: dict, symbol: str) -> None:
    sym = symbol.upper()
    pm = live_meta.get("positions_meta", {}).get(sym)
    if isinstance(pm, dict):
        pm.pop("pending_exit", None)


def get_pending_exit(live_meta: dict, symbol: str) -> dict | None:
    sym = symbol.upper()
    pm = live_meta.get("positions_meta", {}).get(sym, {})
    pe = pm.get("pending_exit") if isinstance(pm, dict) else None
    return pe if isinstance(pe, dict) else None

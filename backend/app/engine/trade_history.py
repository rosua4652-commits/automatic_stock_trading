"""체결 내역 — 업비트 API가 진실(source of truth)."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from app.market.coin_registry import coin_meta
from app.market.upbit_client import upbit_to_symbol
from app.market.upbit_order_fill import (
    parse_upbit_order_fill,
    repair_trade_dict,
    resolve_upbit_fill,
)
from app.models import TradeEvent

if TYPE_CHECKING:
    from app.market.upbit_client import UpbitClient

UPBIT_TRADE_HISTORY_DAYS = 28
UPBIT_TRADE_SYNC_SEC = 25
UPBIT_TRADE_LIMIT = 200


def trade_fingerprint(t: dict[str, Any]) -> tuple:
    uid = str(t.get("order_uuid") or "").strip()
    if uid:
        return ("uuid", uid)
    return (
        "fp",
        round(float(t.get("ts") or 0), 2),
        str(t.get("symbol") or "").upper(),
        str(t.get("side") or "").upper(),
        round(float(t.get("quantity") or 0), 6),
        round(float(t.get("amount_krw") or 0), 0),
    )


def _as_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, TradeEvent):
        return item.model_dump()
    if isinstance(item, dict):
        return dict(item)
    return {}


def merge_trade_dicts(
    *sources: list[Any],
    usdt_krw: float = 1350.0,
    limit: int = UPBIT_TRADE_LIMIT,
) -> list[dict[str, Any]]:
    merged: dict[tuple, dict[str, Any]] = {}
    for src in sources:
        for raw in src or []:
            d = repair_trade_dict(_as_dict(raw), usdt_krw=usdt_krw)
            merged[trade_fingerprint(d)] = d
    rows = sorted(merged.values(), key=lambda x: float(x.get("ts") or 0))
    return rows[-limit:]


def merge_trade_events(
    *sources: list[Any],
    usdt_krw: float = 1350.0,
    limit: int = UPBIT_TRADE_LIMIT,
) -> list[TradeEvent]:
    out: list[TradeEvent] = []
    for d in merge_trade_dicts(*sources, usdt_krw=usdt_krw, limit=limit):
        try:
            out.append(TradeEvent(**d))
        except Exception:
            continue
    return out


def _parse_upbit_ts(raw: Any) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        v = float(raw)
        return v / 1000.0 if v > 1e12 else v
    text = str(raw).strip()
    if not text:
        return 0.0
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return 0.0


def remember_order_reason(
    live_meta: dict[str, Any],
    uuid: str,
    *,
    reason: str,
    is_auto: bool,
) -> None:
    uid = str(uuid or "").strip()
    if not uid:
        return
    bag: dict = live_meta.setdefault("order_reasons", {})
    bag[uid] = {"reason": reason, "is_auto": bool(is_auto)}


def remember_order_uuid(live_meta: dict[str, Any], uuid: str) -> None:
    uid = str(uuid or "").strip()
    if not uid:
        return
    rows = [str(x) for x in (live_meta.get("recorded_order_uuids") or []) if x]
    if uid not in rows:
        rows.append(uid)
    live_meta["recorded_order_uuids"] = rows[-300:]


def _quick_fill_from_list_order(order: dict[str, Any]) -> tuple[float, float, float]:
    qty = float(order.get("executed_volume") or 0)
    if qty <= 1e-12:
        return 0.0, 0.0, 0.0
    if order.get("trades"):
        return parse_upbit_order_fill(order)
    side = str(order.get("side") or "").lower()
    ord_type = str(order.get("ord_type") or "").lower()
    price = float(order.get("price") or 0)
    if side == "bid" and ord_type == "price" and price > 0:
        return qty, price, price / qty
    if price > 0 and ord_type in ("limit", "best"):
        funds = price * qty
        return qty, funds, price
    return qty, 0.0, 0.0


def _default_reason(side: str, ord_type: str) -> str:
    if side == "BUY":
        if ord_type == "price":
            return "업비트 시장가 매수"
        return "업비트 매수"
    if ord_type in ("market", "best"):
        return "업비트 시장가 매도"
    return "업비트 매도"


async def _fetch_closed_done_orders(
    client: "UpbitClient",
    *,
    days: int = UPBIT_TRADE_HISTORY_DAYS,
) -> list[dict]:
    """7일 단위 closed API — 최대 days일치 done 주문."""
    by_uuid: dict[str, dict] = {}
    end = datetime.now(timezone.utc)
    remaining = max(days, 1)

    while remaining > 0:
        window = min(7, remaining)
        start = end - timedelta(days=window)
        batch: list[dict] = []
        try:
            batch = await client.closed_orders(
                start_time=start.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                end_time=end.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                limit=1000,
                states=["done"],
            )
        except Exception:
            page = 1
            while page <= 5:
                legacy = await client.done_orders(limit=100, page=page)
                if not legacy:
                    break
                batch.extend(legacy)
                if len(legacy) < 100:
                    break
                page += 1
            break

        for row in batch:
            uid = str(row.get("uuid") or "")
            if uid:
                by_uuid[uid] = row
        end = start
        remaining -= window
        if not batch:
            break

    return list(by_uuid.values())


async def _enrich_orders_with_trades(
    client: "UpbitClient", orders: list[dict]
) -> list[dict]:
    need: list[str] = []
    for order in orders:
        qty, funds, _ = _quick_fill_from_list_order(order)
        if qty > 1e-12 and funds <= 0:
            uid = str(order.get("uuid") or "")
            if uid:
                need.append(uid)

    detail: dict[str, dict] = {}
    for i in range(0, len(need), 100):
        chunk = need[i : i + 100]
        try:
            rows = await client.orders_by_uuids(chunk)
        except Exception:
            for uid in chunk:
                try:
                    row = await client.get_order(uid)
                    if row:
                        detail[str(uid)] = row
                except Exception:
                    continue
            continue
        for row in rows:
            uid = str(row.get("uuid") or "")
            if uid:
                detail[uid] = row

    out: list[dict] = []
    for order in orders:
        uid = str(order.get("uuid") or "")
        merged = {**order, **detail.get(uid, {})} if uid in detail else dict(order)
        out.append(merged)
    return out


async def _order_to_trade(
    client: "UpbitClient",
    order: dict[str, Any],
    *,
    usdt_krw: float,
    reason_hints: dict[str, dict[str, Any]],
) -> TradeEvent | None:
    qty_raw = float(order.get("executed_volume") or 0)
    if qty_raw <= 1e-12:
        return None

    uid = str(order.get("uuid") or "")
    side_raw = str(order.get("side") or "").lower()
    side = "BUY" if side_raw == "bid" else "SELL"
    ord_type = str(order.get("ord_type") or "").lower()
    hint = reason_hints.get(uid) or {}
    reason = str(hint.get("reason") or _default_reason(side, ord_type))
    is_auto = bool(hint.get("is_auto", False))

    qty, funds, px_krw = _quick_fill_from_list_order(order)
    if funds <= 0 or px_krw <= 0:
        try:
            qty, funds, px_krw = await resolve_upbit_fill(
                client,
                order,
                fallback_qty=qty_raw,
            )
        except Exception:
            qty, funds, px_krw = qty_raw, 0.0, 0.0

    if qty <= 1e-12:
        return None

    market = str(order.get("market") or "")
    if not market.startswith("KRW-"):
        return None
    symbol = upbit_to_symbol(market).upper()
    m = coin_meta(symbol)
    rate = max(usdt_krw, 1.0)
    ts = _parse_upbit_ts(order.get("created_at")) or time.time()

    row = repair_trade_dict(
        {
            "ts": ts,
            "symbol": symbol,
            "base": m["base"],
            "display": m["display"],
            "side": side,
            "price": px_krw / rate if px_krw > 0 else 0.0,
            "price_krw": round(px_krw, 4) if px_krw > 0 else 0.0,
            "quantity": qty,
            "amount_krw": round(funds, 0) if funds > 0 else 0.0,
            "amount_usdt": round(funds / rate, 4) if funds > 0 else 0.0,
            "reason": reason,
            "is_auto": is_auto,
            "order_uuid": uid,
        },
        usdt_krw=rate,
    )
    try:
        return TradeEvent(**row)
    except Exception:
        return None


async def load_trades_from_upbit(
    client: "UpbitClient",
    live_meta: dict[str, Any],
    *,
    usdt_krw: float,
    force: bool = False,
) -> list[TradeEvent]:
    """
    업비트 done/closed 주문 → 매매 내역.
    AIDI 로컬 기록 대신 거래소가 진실.
    """
    now = time.time()
    last = float(live_meta.get("trades_upbit_synced_at") or 0)
    cached = live_meta.get("trades") or []
    if (
        not force
        and cached
        and now - last < UPBIT_TRADE_SYNC_SEC
    ):
        return merge_trade_events(cached, usdt_krw=usdt_krw, limit=UPBIT_TRADE_LIMIT)

    orders = await _fetch_closed_done_orders(client)
    orders = [
        o
        for o in orders
        if float(o.get("executed_volume") or 0) > 1e-12
        and str(o.get("market") or "").startswith("KRW-")
    ]
    orders = await _enrich_orders_with_trades(client, orders)

    hints: dict[str, dict[str, Any]] = {}
    raw_hints = live_meta.get("order_reasons") or {}
    if isinstance(raw_hints, dict):
        for k, v in raw_hints.items():
            if isinstance(v, dict):
                hints[str(k)] = v

    trades: list[TradeEvent] = []
    for order in orders:
        evt = await _order_to_trade(
            client, order, usdt_krw=usdt_krw, reason_hints=hints
        )
        if evt:
            trades.append(evt)
            if evt.order_uuid:
                remember_order_uuid(live_meta, evt.order_uuid)

    trades.sort(key=lambda t: t.ts)
    trades = trades[-UPBIT_TRADE_LIMIT:]
    live_meta["trades_upbit_synced_at"] = now
    live_meta["trades"] = [t.model_dump() for t in trades]
    return trades

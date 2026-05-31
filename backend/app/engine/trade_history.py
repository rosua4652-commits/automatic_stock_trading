"""체결 내역 — 업비트 주문 API (state=done) 가 진실."""

from __future__ import annotations

import asyncio
import logging
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

logger = logging.getLogger(__name__)

UPBIT_TRADE_HISTORY_DAYS = 28
UPBIT_TRADE_SYNC_SEC = 8
UPBIT_TRADE_LIMIT = 200
DONE_ORDER_MAX_PAGES = 30


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


def _f(val: Any) -> float:
    try:
        return float(val or 0)
    except (TypeError, ValueError):
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


def _default_reason(side: str, ord_type: str) -> str:
    if side == "BUY":
        if ord_type == "price":
            return "업비트 시장가 매수"
        return "업비트 매수"
    if ord_type in ("market", "best"):
        return "업비트 시장가 매도"
    return "업비트 매도"


def _fill_from_order(order: dict[str, Any]) -> tuple[float, float, float]:
    """(qty, amount_krw, price_krw) — 목록 응답만으로 최대한 채움."""
    qty = _f(order.get("executed_volume"))
    if qty <= 1e-12:
        return 0.0, 0.0, 0.0

    if order.get("trades"):
        return parse_upbit_order_fill(order)

    side = str(order.get("side") or "").lower()
    ord_type = str(order.get("ord_type") or "").lower()
    price = _f(order.get("price"))

    # 시장가 매수: price 필드 = 총 매수 금액(KRW)
    if side == "bid" and ord_type == "price" and price > 0:
        return qty, price, price / qty

    # 지정가·IOC 등: price = 호가
    if price > 0 and ord_type in ("limit", "best"):
        funds = price * qty
        return qty, funds, price

    # 시장가 매도: paid_fee만 있고 trades 없음 → 상세 조회 필요
    return qty, 0.0, 0.0


async def fetch_done_orders_paginated(
    client: "UpbitClient",
    *,
    max_pages: int = DONE_ORDER_MAX_PAGES,
) -> list[dict]:
    """
    GET /v1/orders?state=done — 업비트 앱 체결내역과 동일 소스.
    closed API 실패/빈 응답 이슈를 피하기 위해 이 API만 우선 사용.
    """
    by_uuid: dict[str, dict] = {}
    cutoff = time.time() - UPBIT_TRADE_HISTORY_DAYS * 86400

    for page in range(1, max_pages + 1):
        try:
            batch = await client.done_orders(limit=100, page=page)
        except Exception as e:
            logger.warning("upbit done_orders page=%s failed: %s", page, e)
            break
        if not batch:
            break
        page_has_recent = False
        for row in batch:
            if _f(row.get("executed_volume")) <= 1e-12:
                continue
            market = str(row.get("market") or "")
            if not market.startswith("KRW-"):
                continue
            ts = _parse_upbit_ts(row.get("created_at"))
            if ts > 0 and ts < cutoff:
                continue
            page_has_recent = True
            uid = str(row.get("uuid") or "")
            if uid:
                by_uuid[uid] = row
        if not page_has_recent:
            break
        if len(batch) < 100:
            break

    return list(by_uuid.values())


async def _fetch_closed_supplement(
    client: "UpbitClient",
    existing: set[str],
) -> list[dict]:
    """done 목록이 비었을 때만 closed API 시도."""
    extra: list[dict] = []
    kst = timezone(timedelta(hours=9))
    end = datetime.now(kst)
    start = end - timedelta(days=7)
    try:
        batch = await client.closed_orders(
            start_time=start.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            end_time=end.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            limit=1000,
            states=["done"],
        )
    except Exception as e:
        logger.warning("upbit closed_orders failed: %s", e)
        return []
    for row in batch:
        uid = str(row.get("uuid") or "")
        if uid and uid not in existing and _f(row.get("executed_volume")) > 0:
            if str(row.get("market") or "").startswith("KRW-"):
                extra.append(row)
    return extra


async def _enrich_orders(
    client: "UpbitClient", orders: list[dict]
) -> list[dict]:
    """체결금액 없는 주문만 상세(trades[]) 조회."""
    need: list[str] = []
    for order in orders:
        qty, funds, _ = _fill_from_order(order)
        if qty > 1e-12 and funds <= 0:
            uid = str(order.get("uuid") or "")
            if uid:
                need.append(uid)
    if not need:
        return orders

    detail: dict[str, dict] = {}
    for i in range(0, len(need), 100):
        chunk = need[i : i + 100]
        try:
            rows = await client.orders_by_uuids(chunk)
            if isinstance(rows, dict):
                rows = [rows]
            for row in rows or []:
                uid = str(row.get("uuid") or "")
                if uid:
                    detail[uid] = row
        except Exception:
            sem = asyncio.Semaphore(8)

            async def _one(u: str) -> None:
                async with sem:
                    try:
                        row = await client.get_order(u)
                        if row:
                            detail[u] = row
                    except Exception:
                        pass

            await asyncio.gather(*[_one(u) for u in chunk])

    out: list[dict] = []
    for order in orders:
        uid = str(order.get("uuid") or "")
        if uid in detail:
            merged = {**order, **detail[uid]}
            if detail[uid].get("trades"):
                merged["trades"] = detail[uid]["trades"]
            out.append(merged)
        else:
            out.append(order)
    return out


def order_to_trade_dict(
    order: dict[str, Any],
    *,
    usdt_krw: float,
    reason_hints: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    qty_raw = _f(order.get("executed_volume"))
    if qty_raw <= 1e-12:
        return None

    market = str(order.get("market") or "")
    if not market.startswith("KRW-"):
        return None

    uid = str(order.get("uuid") or "")
    side_raw = str(order.get("side") or "").lower()
    side = "BUY" if side_raw == "bid" else "SELL"
    ord_type = str(order.get("ord_type") or "").lower()
    hint = reason_hints.get(uid) or {}
    reason = str(hint.get("reason") or _default_reason(side, ord_type))
    is_auto = bool(hint.get("is_auto", False))

    qty, funds, px_krw = _fill_from_order(order)
    if qty <= 1e-12:
        return None

    symbol = upbit_to_symbol(market).upper()
    m = coin_meta(symbol)
    rate = max(usdt_krw, 1.0)
    ts = _parse_upbit_ts(order.get("created_at")) or time.time()

    return repair_trade_dict(
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


async def _order_to_trade(
    client: "UpbitClient",
    order: dict[str, Any],
    *,
    usdt_krw: float,
    reason_hints: dict[str, dict[str, Any]],
) -> TradeEvent | None:
    row = order_to_trade_dict(order, usdt_krw=usdt_krw, reason_hints=reason_hints)
    if not row:
        return None

    qty = _f(row.get("quantity"))
    funds = _f(row.get("amount_krw"))
    if funds <= 0 or _f(row.get("price_krw")) <= 0:
        try:
            q2, f2, p2 = await resolve_upbit_fill(
                client,
                order,
                fallback_qty=qty,
            )
            if q2 > 0:
                row["quantity"] = q2
            if f2 > 0:
                row["amount_krw"] = round(f2, 0)
                row["amount_usdt"] = round(f2 / max(usdt_krw, 1.0), 4)
            if p2 > 0:
                row["price_krw"] = round(p2, 4)
                row["price"] = p2 / max(usdt_krw, 1.0)
            row = repair_trade_dict(row, usdt_krw=usdt_krw)
        except Exception:
            pass

    try:
        return TradeEvent(**row)
    except Exception as e:
        logger.debug("TradeEvent skip %s: %s", order.get("uuid"), e)
        return None


async def load_trades_from_upbit(
    client: "UpbitClient",
    live_meta: dict[str, Any],
    *,
    usdt_krw: float,
    force: bool = False,
) -> list[TradeEvent]:
    """업비트 매수·매도 체결 → 매매 내역 (최근 28일)."""
    now = time.time()
    last = float(live_meta.get("trades_upbit_synced_at") or 0)
    cached = live_meta.get("trades") or []

    if (
        not force
        and cached
        and now - last < UPBIT_TRADE_SYNC_SEC
    ):
        return merge_trade_events(cached, usdt_krw=usdt_krw, limit=UPBIT_TRADE_LIMIT)

    prev_events = merge_trade_events(cached, usdt_krw=usdt_krw, limit=UPBIT_TRADE_LIMIT)

    try:
        orders = await fetch_done_orders_paginated(client)
        if not orders:
            orders = await _fetch_closed_supplement(client, set())

        orders = await _enrich_orders(client, orders)

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

        if trades:
            live_meta["trades_upbit_synced_at"] = now
            live_meta["trades"] = [t.model_dump() for t in trades]
            live_meta.pop("trades_sync_error", None)
            return trades

        live_meta["trades_sync_error"] = (
            "업비트 체결 주문이 없거나 API 조회 권한을 확인하세요"
        )
        live_meta.pop("trades_upbit_synced_at", None)
        if prev_events:
            return prev_events
        return []

    except Exception as e:
        logger.exception("load_trades_from_upbit failed")
        live_meta["trades_sync_error"] = str(e)[:200]
        live_meta.pop("trades_upbit_synced_at", None)
        if prev_events:
            return prev_events
        return []

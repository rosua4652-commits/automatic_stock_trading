"""체결 내역 — 업비트 주문 API + 로컬 메타 병합."""

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

UPBIT_TRADE_HISTORY_DAYS = 90
UPBIT_TRADE_LIMIT = 500
DONE_ORDER_MAX_PAGES = 50
ORDER_REASONS_KEEP = 800
EXIT_LOG_KEEP = 600


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


def _trade_reason_score(d: dict[str, Any]) -> int:
    """병합 시 익절/손절·승인 라벨이 수동 라벨보다 우선."""
    side = str(d.get("side") or "").upper()
    reason = str(d.get("reason") or "")
    ek = str(d.get("exit_kind") or "").lower()
    if not ek and side == "SELL":
        ek = classify_exit_kind(reason, side)
    if side == "SELL":
        if ek in ("tp", "sl") or reason in ("익절", "손절"):
            return 4
        if reason == "수동 매도":
            return 1
        return 2
    if side == "BUY":
        if ek == "approval" or "승인" in reason:
            return 4
        if reason == "수동 매수":
            return 1
        return 2
    return 0


def _prefer_trade_row(
    incoming: dict[str, Any], existing: dict[str, Any]
) -> dict[str, Any]:
    if _trade_reason_score(incoming) > _trade_reason_score(existing):
        return incoming
    if _trade_reason_score(incoming) < _trade_reason_score(existing):
        return existing
    return incoming


def merge_trade_dicts(
    *sources: list[Any],
    usdt_krw: float = 1350.0,
    limit: int = UPBIT_TRADE_LIMIT,
) -> list[dict[str, Any]]:
    merged: dict[tuple, dict[str, Any]] = {}
    for src in sources:
        for raw in src or []:
            d = repair_trade_dict(_as_dict(raw), usdt_krw=usdt_krw)
            fp = trade_fingerprint(d)
            if fp in merged:
                merged[fp] = _prefer_trade_row(d, merged[fp])
            else:
                merged[fp] = d
    rows = sorted(merged.values(), key=lambda x: float(x.get("ts") or 0))
    return rows[-limit:]


def merge_trade_events(
    *sources: list[Any],
    usdt_krw: float = 1350.0,
    limit: int = UPBIT_TRADE_LIMIT,
) -> list[TradeEvent]:
    out: list[TradeEvent] = []
    for d in merge_trade_dicts(*sources, usdt_krw=usdt_krw, limit=limit):
        evt = dict_to_trade_event(d, usdt_krw=usdt_krw)
        if evt:
            out.append(evt)
    return out


def dict_to_trade_event(
    raw: dict[str, Any], *, usdt_krw: float = 1350.0
) -> TradeEvent | None:
    d = repair_trade_dict(_as_dict(raw), usdt_krw=usdt_krw)
    sym = str(d.get("symbol") or "").upper()
    if not sym:
        return None
    m = coin_meta(sym)
    if not d.get("base"):
        d["base"] = m["base"]
    if not d.get("display"):
        d["display"] = m["display"]
    if not d.get("side"):
        return None
    uid = str(d.get("order_uuid") or "")
    side_row = str(d.get("side") or "")
    exit_kind = str(d.get("exit_kind") or "").lower()
    if not exit_kind and side_row.upper() == "SELL":
        exit_kind = classify_exit_kind(str(d.get("reason") or ""), side_row)
    raw_reason = str(d.get("reason") or "")
    has_hint = bool(uid) and (
        exit_kind in ("tp", "sl", "approval", "manual")
        or raw_reason not in ("", "수동 매도", "수동 매수")
        or bool(d.get("is_auto"))
    )
    d["reason"] = normalize_trade_reason(
        side_row,
        raw_reason,
        is_auto=bool(d.get("is_auto")),
        has_aidi_hint=has_hint,
        exit_kind=exit_kind,
    )
    if exit_kind:
        d["exit_kind"] = exit_kind
    try:
        return TradeEvent(**d)
    except Exception as e:
        logger.debug("TradeEvent skip %s: %s", sym, e)
        return None


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


def _hint_applies_to_side(hint: dict[str, Any], side: str) -> bool:
    """매도 전용 사유(익절/손절)가 매수 주문 UUID에 붙는 것 방지."""
    if not hint:
        return False
    side_u = str(side or "").upper()
    hs = str(hint.get("side") or "").upper()
    if hs and hs != side_u:
        return False
    ek = str(hint.get("exit_kind") or "").lower()
    text = str(hint.get("reason") or "")
    if ek in ("tp", "sl") or "익절" in text or "손절" in text or "급락" in text:
        return side_u == "SELL"
    return True


def classify_exit_kind(reason: str, side: str) -> str:
    """tp | sl | manual | approval | auto | ''"""
    text = (reason or "").strip()
    is_buy = str(side).upper() == "BUY"
    if is_buy:
        # 매수 사유에 붙는 「손절 3% / 익절 5%」 목표 문구는 청산 유형이 아님
        if "자동투자" in text or "자동 매수" in text:
            return "auto"
        if "승인" in text:
            return "approval"
        if "수동" in text:
            return "manual"
        return ""
    if "익절" in text:
        return "tp"
    if "손절" in text or "급락" in text:
        return "sl"
    if "수동" in text:
        return "manual"
    return ""


def normalize_trade_reason(
    side: str,
    raw_reason: str,
    *,
    is_auto: bool = False,
    has_aidi_hint: bool = False,
    exit_kind: str = "",
) -> str:
    """
    익절 · 손절 · 수동 매수 · 수동 매도 · 승인 매수
    손익절 설정·자동 감시 매도 → 익절/손절 (수동 매도 아님)
    업비트만 체결·AIDI 로그 없음 → 수동 매수/매도
    """
    text = (raw_reason or "").strip()
    is_buy = str(side).upper() == "BUY"
    kind = (exit_kind or "").lower()

    # 익절·손절은 매도(SELL)에만 — 매수에 잘못 붙은 힌트는 무시
    if is_buy:
        if kind in ("tp", "sl") or "익절" in text or "손절" in text or "급락" in text:
            text = ""
            kind = ""
    elif kind == "tp" or "익절" in text:
        return "익절"
    elif kind == "sl" or "손절" in text or "급락" in text:
        return "손절"

    if is_buy:
        if not has_aidi_hint:
            return "수동 매수"
        if kind == "auto" or "자동투자" in text or "자동 매수" in text:
            return "자동 매수"
        if kind == "approval" or "승인" in text:
            return "승인 매수"
        if kind == "manual" or "수동" in text:
            return "수동 매수"
        return "자동 매수" if is_auto else "수동 매수"

    if not has_aidi_hint:
        return "수동 매도"
    if kind == "manual" or (
        "수동" in text and kind not in ("tp", "sl") and "익절" not in text and "손절" not in text
    ):
        return "수동 매도"
    # 손익절 감시·설정 매도 (전량 매도 시 is_auto=False 여도 exit_kind/사유로 구분)
    if kind in ("tp", "sl") or is_auto:
        if kind == "sl" or "손절" in text or "급락" in text:
            return "손절"
        if kind == "tp" or "익절" in text:
            return "익절"
    return "수동 매도"


def _order_reason_hint(
    live_meta: dict[str, Any], uid: str, side: str
) -> dict[str, Any]:
    """주문 UUID에 저장된 사유 — 매수 목표 손익절 문구와 매도 청산을 구분."""
    if not uid:
        return {}
    raw = live_meta.get("order_reasons") or {}
    row = raw.get(uid) if isinstance(raw, dict) else None
    if not isinstance(row, dict):
        return {}
    side_u = str(side or "").upper()
    hs = str(row.get("side") or "").upper()
    if hs and hs != side_u:
        return {}
    hint = dict(row)
    if side_u == "BUY" and str(hint.get("exit_kind") or "").lower() in ("tp", "sl"):
        hint["exit_kind"] = classify_exit_kind(str(hint.get("reason") or ""), "BUY")
    if not _hint_applies_to_side(hint, side_u):
        return {}
    return hint


def collect_reason_hints(live_meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """order_reasons + exit_log + pending 지정가 + 저장된 체결 메타."""
    hints: dict[str, dict[str, Any]] = {}
    raw = live_meta.get("order_reasons") or {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, dict):
                hints[str(k)] = dict(v)

    for row in live_meta.get("exit_log") or []:
        if not isinstance(row, dict):
            continue
        uid = str(row.get("order_uuid") or "")
        if uid and uid not in hints:
            hints[uid] = {
                "reason": str(row.get("reason") or ""),
                "is_auto": bool(row.get("is_auto")),
                "side": str(row.get("side") or "SELL").upper(),
                "exit_kind": str(row.get("exit_kind") or ""),
            }

    for pm in (live_meta.get("positions_meta") or {}).values():
        if not isinstance(pm, dict):
            continue
        pe = pm.get("pending_exit")
        if isinstance(pe, dict):
            uid = str(pe.get("order_uuid") or "")
            if uid:
                hints[uid] = {
                    "reason": str(pe.get("reason") or "손절"),
                    "is_auto": True,
                    "side": "SELL",
                    "exit_kind": str(pe.get("exit_kind") or ""),
                }

    for row in live_meta.get("trades") or []:
        d = _as_dict(row)
        uid = str(d.get("order_uuid") or "")
        if uid and uid not in hints and d.get("reason"):
            reason = str(d.get("reason"))
            side = str(d.get("side") or "").upper()
            ek = str(d.get("exit_kind") or "").lower() or classify_exit_kind(
                reason, side
            )
            if (
                side == "SELL"
                and reason == "수동 매도"
                and bool(d.get("is_auto"))
                and ek == "manual"
            ):
                continue
            hints[uid] = {
                "reason": reason,
                "is_auto": bool(d.get("is_auto")),
                "side": side,
                "exit_kind": ek,
            }
    return hints


def remember_order_reason(
    live_meta: dict[str, Any],
    uuid: str,
    *,
    reason: str,
    is_auto: bool,
    side: str = "",
    symbol: str = "",
    persist: bool = False,
) -> None:
    uid = str(uuid or "").strip()
    if not uid:
        return
    bag: dict = live_meta.setdefault("order_reasons", {})
    if side:
        side_u = str(side).upper()
    elif "매도" in reason:
        side_u = "SELL"
    elif "매수" in reason or "승인" in reason or "자동투자" in reason:
        side_u = "BUY"
    elif "익절" in reason or "손절" in reason or "급락" in reason:
        side_u = "SELL"
    else:
        side_u = "BUY"
    exit_kind = classify_exit_kind(reason, side_u)
    bag[uid] = {
        "reason": reason,
        "is_auto": bool(is_auto),
        "side": side_u,
        "exit_kind": exit_kind,
    }
    if len(bag) > ORDER_REASONS_KEEP:
        for key in list(bag.keys())[: len(bag) - ORDER_REASONS_KEEP]:
            del bag[key]
    if side_u == "SELL" and exit_kind in ("tp", "sl"):
        log = live_meta.setdefault("exit_log", [])
        log.append(
            {
                "order_uuid": uid,
                "symbol": str(symbol or "").upper(),
                "reason": reason,
                "is_auto": bool(is_auto),
                "side": side_u,
                "exit_kind": exit_kind,
                "ts": time.time(),
            }
        )
        live_meta["exit_log"] = log[-EXIT_LOG_KEEP:]
    if persist:
        try:
            from app.storage.persistence import save_live_meta

            save_live_meta(live_meta)
        except Exception:
            logger.debug("save_live_meta after order reason failed", exc_info=True)


def remember_order_uuid(live_meta: dict[str, Any], uuid: str) -> None:
    uid = str(uuid or "").strip()
    if not uid:
        return
    rows = [str(x) for x in (live_meta.get("recorded_order_uuids") or []) if x]
    if uid not in rows:
        rows.append(uid)
    live_meta["recorded_order_uuids"] = rows[-300:]


def _fill_from_order(order: dict[str, Any]) -> tuple[float, float, float]:
    """(qty, amount_krw, price_krw)"""
    qty = _f(order.get("executed_volume"))
    if qty <= 1e-12:
        qty = _f(order.get("volume"))

    if qty <= 1e-12:
        return 0.0, 0.0, 0.0

    if order.get("trades"):
        return parse_upbit_order_fill(order)

    side = str(order.get("side") or "").lower()
    ord_type = str(order.get("ord_type") or "").lower()
    price = _f(order.get("price"))

    if side == "bid" and ord_type == "price" and price > 0:
        return qty, price, price / max(qty, 1e-12)

    if price > 0 and ord_type in ("limit", "best"):
        return qty, price * qty, price

    if side == "ask" and ord_type == "market" and price > 0:
        return qty, price * qty, price

    return qty, 0.0, 0.0


async def fetch_done_orders_paginated(
    client: "UpbitClient",
    *,
    max_pages: int = DONE_ORDER_MAX_PAGES,
) -> list[dict]:
    """GET /v1/orders?state=done — 페이지 끝까지 수집 (조기 중단 없음)."""
    by_uuid: dict[str, dict] = {}
    last_err: str | None = None

    for page in range(1, max_pages + 1):
        try:
            batch = await client.done_orders(limit=100, page=page)
        except Exception as e:
            last_err = str(e)
            logger.warning("upbit done_orders page=%s: %s", page, e)
            break
        if not batch:
            break
        for row in batch:
            market = str(row.get("market") or "")
            if not market.startswith("KRW-"):
                continue
            uid = str(row.get("uuid") or "")
            if uid:
                by_uuid[uid] = row
        if len(batch) < 100:
            break

    if not by_uuid and last_err:
        raise RuntimeError(last_err)
    return list(by_uuid.values())


async def _fetch_closed_orders(
    client: "UpbitClient",
    *,
    days: int = UPBIT_TRADE_HISTORY_DAYS,
) -> list[dict]:
    """7일 구간씩 closed API (최대 days일)."""
    by_uuid: dict[str, dict] = {}
    kst = timezone(timedelta(hours=9))
    end = datetime.now(kst)
    remaining = max(days, 1)

    while remaining > 0:
        window = min(7, remaining)
        start = end - timedelta(days=window)
        try:
            batch = await client.closed_orders(
                start_time=start.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                end_time=end.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                limit=1000,
                states=["done"],
            )
        except Exception as e:
            logger.warning("upbit closed_orders: %s", e)
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


async def _enrich_orders(
    client: "UpbitClient", orders: list[dict]
) -> list[dict]:
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
            sem = asyncio.Semaphore(10)

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
    market = str(order.get("market") or "")
    if not market.startswith("KRW-"):
        return None

    uid = str(order.get("uuid") or "")
    side_raw = str(order.get("side") or "").lower()
    side = "BUY" if side_raw == "bid" else "SELL"
    ord_type = str(order.get("ord_type") or "").lower()
    hint = dict(reason_hints.get(uid) or {})
    if side == "BUY" and str(hint.get("exit_kind") or "").lower() in ("tp", "sl"):
        hint["exit_kind"] = classify_exit_kind(str(hint.get("reason") or ""), "BUY")
    if not _hint_applies_to_side(hint, side):
        hint = {}
    raw_reason = str(hint.get("reason") or "")
    is_auto = bool(hint.get("is_auto", False))
    has_hint = bool(uid and hint)
    reason = normalize_trade_reason(
        side,
        raw_reason,
        is_auto=is_auto,
        has_aidi_hint=has_hint,
        exit_kind=str(hint.get("exit_kind") or ""),
    )

    qty, funds, px_krw = _fill_from_order(order)
    if qty <= 1e-12:
        return None

    symbol = upbit_to_symbol(market).upper()
    m = coin_meta(symbol)
    rate = max(usdt_krw, 1.0)
    ts = _parse_upbit_ts(order.get("created_at")) or time.time()

    mode = ""
    if side == "BUY":
        from app.engine.live_position_meta import entry_mode_label, outlook_from_reason_text

        mode = entry_mode_label(
            outlook_from_reason_text(raw_reason) or outlook_from_reason_text(reason)
        )
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
            "entry_mode": mode,
        },
        usdt_krw=rate,
    )


async def _resolve_one(
    client: "UpbitClient",
    order: dict[str, Any],
    row: dict[str, Any],
    *,
    usdt_krw: float,
) -> dict[str, Any]:
    if _f(row.get("amount_krw")) > 0 and _f(row.get("price_krw")) > 0:
        return row
    try:
        qty = _f(row.get("quantity"))
        q2, f2, p2 = await resolve_upbit_fill(
            client, order, fallback_qty=qty
        )
        if q2 > 0:
            row["quantity"] = q2
        if f2 > 0:
            row["amount_krw"] = round(f2, 0)
            row["amount_usdt"] = round(f2 / max(usdt_krw, 1.0), 4)
        if p2 > 0:
            row["price_krw"] = round(p2, 4)
            row["price"] = p2 / max(usdt_krw, 1.0)
    except Exception:
        pass
    return repair_trade_dict(row, usdt_krw=usdt_krw)


async def orders_to_trades(
    client: "UpbitClient",
    orders: list[dict],
    *,
    usdt_krw: float,
    reason_hints: dict[str, dict[str, Any]],
) -> list[TradeEvent]:
    cutoff = time.time() - UPBIT_TRADE_HISTORY_DAYS * 86400
    rows: list[dict[str, Any]] = []

    for order in orders:
        d = order_to_trade_dict(order, usdt_krw=usdt_krw, reason_hints=reason_hints)
        if not d:
            continue
        ts = _f(d.get("ts"))
        if ts > 0 and ts < cutoff:
            continue
        rows.append(d)

    sem = asyncio.Semaphore(12)

    async def _fill(row: dict, order: dict) -> dict:
        async with sem:
            return await _resolve_one(client, order, row, usdt_krw=usdt_krw)

    order_by_uid = {str(o.get("uuid") or ""): o for o in orders}
    filled = await asyncio.gather(
        *[
            _fill(row, order_by_uid.get(str(row.get("order_uuid") or ""), {}))
            for row in rows
        ]
    )

    out: list[TradeEvent] = []
    for row in filled:
        evt = dict_to_trade_event(row, usdt_krw=usdt_krw)
        if evt:
            out.append(evt)
    return out


async def load_trades_from_upbit(
    client: "UpbitClient",
    live_meta: dict[str, Any],
    *,
    usdt_krw: float,
    force: bool = False,
) -> list[TradeEvent]:
    """업비트 체결 + 기존 저장본 병합 — 비어도 예전 기록 유지."""
    cached = live_meta.get("trades") or []
    prev = merge_trade_events(cached, usdt_krw=usdt_krw, limit=UPBIT_TRADE_LIMIT)

    hints = collect_reason_hints(live_meta)

    api_trades: list[TradeEvent] = []
    err_msg: str | None = None
    orders_fetched = 0

    try:
        orders = await fetch_done_orders_paginated(client)
        closed = await _fetch_closed_orders(client)
        by_uid = {str(o.get("uuid") or ""): o for o in orders}
        for row in closed:
            uid = str(row.get("uuid") or "")
            if uid and uid not in by_uid:
                if str(row.get("market") or "").startswith("KRW-"):
                    by_uid[uid] = row
        orders = list(by_uid.values())
        orders_fetched = len(orders)
        orders = await _enrich_orders(client, orders)
        api_trades = await orders_to_trades(
            client, orders, usdt_krw=usdt_krw, reason_hints=hints
        )
        live_meta["trades_orders_fetched"] = orders_fetched
        for t in api_trades:
            if t.order_uuid:
                remember_order_uuid(live_meta, t.order_uuid)
    except Exception as e:
        logger.exception("upbit trades fetch failed")
        err_msg = str(e)[:220]

    combined = merge_trade_events(
        cached,
        [t.model_dump() for t in api_trades],
        usdt_krw=usdt_krw,
        limit=UPBIT_TRADE_LIMIT,
    )

    if not combined and prev:
        combined = prev

    if err_msg and not api_trades:
        live_meta["trades_sync_error"] = err_msg
    elif not combined:
        live_meta["trades_sync_error"] = (
            "업비트 체결 주문이 없습니다. 최근 KRW 마켓 매매가 있는지 확인하세요."
        )
    else:
        live_meta.pop("trades_sync_error", None)

    live_meta["trades_upbit_synced_at"] = time.time()
    merged_rows = merge_trade_dicts(
        [t.model_dump() for t in combined],
        usdt_krw=usdt_krw,
        limit=UPBIT_TRADE_LIMIT,
    )
    for row in merged_rows:
        uid = str(row.get("order_uuid") or "")
        side_row = str(row.get("side") or "")
        hint_row = _order_reason_hint(live_meta, uid, side_row) or dict(
            hints.get(uid) or {}
        )
        if not _hint_applies_to_side(hint_row, side_row):
            hint_row = {}
        exit_kind = str(
            hint_row.get("exit_kind")
            or row.get("exit_kind")
            or classify_exit_kind(
                str(hint_row.get("reason") or row.get("reason") or ""),
                side_row,
            )
        )
        raw_reason = str(hint_row.get("reason") or row.get("reason") or "")
        if hint_row:
            row["is_auto"] = bool(hint_row.get("is_auto", row.get("is_auto")))
        has_hint = bool(uid and hint_row)
        row["exit_kind"] = exit_kind
        row["reason"] = normalize_trade_reason(
            side_row,
            raw_reason,
            is_auto=bool(row.get("is_auto")),
            has_aidi_hint=has_hint,
            exit_kind=exit_kind,
        )
    live_meta["trades"] = merged_rows
    live_meta["trades_display_count"] = len(merged_rows)
    return merge_trade_events(merged_rows, usdt_krw=usdt_krw, limit=UPBIT_TRADE_LIMIT)

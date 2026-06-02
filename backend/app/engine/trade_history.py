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
DONE_ORDER_MAX_PAGES_NORMAL = 4
TRADES_SYNC_COOLDOWN_SEC = 120
ORDER_REASONS_KEEP = 800
EXIT_LOG_KEEP = 600


def _is_upbit_rate_limit(err: BaseException | str) -> bool:
    text = str(err).lower()
    return "too_many_requests" in text or "429" in text


async def _wait_rate_limit(attempt: int, *, context: str = "") -> None:
    from app.engine.market_health import report_rate_limit

    wait = min(12.0, 0.6 * (2**attempt))
    detail = f"체결 조회 {context}".strip() if context else "체결 조회"
    report_rate_limit(detail, retry_sec=wait + 30.0)
    await asyncio.sleep(wait)


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


def _is_weak_manual_sell_hint(hint: dict[str, Any]) -> bool:
    """업비트 동기화만 된 '수동 매도' — exit_log·order_reasons가 우선."""
    if not hint:
        return False
    side = str(hint.get("side") or "SELL").upper()
    if side != "SELL":
        return False
    ek = str(hint.get("exit_kind") or "").lower()
    if ek in ("tp", "sl"):
        return False
    text = str(hint.get("reason") or "").strip()
    return ek in ("", "manual") and text in ("", "수동 매도", "manual")


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


def resolve_sell_entry_mode(
    live_meta: dict[str, Any],
    *,
    symbol: str,
    row: dict[str, Any] | None = None,
) -> str:
    """매도 체결 — 해당 종목 진입 유형(롱/단타) 추론."""
    if row and str(row.get("entry_mode") or "").strip():
        return str(row["entry_mode"]).strip()

    from app.engine.live_position_meta import entry_mode_label, infer_recent_aidi_buy

    sym = str(symbol or "").upper()
    if not sym:
        return ""

    pm = (live_meta.get("positions_meta") or {}).get(sym) or {}
    outlook = str(pm.get("entry_outlook") or "")
    if outlook:
        label = entry_mode_label(outlook)
        if label:
            return label

    inferred = infer_recent_aidi_buy(live_meta, sym)
    if inferred:
        return entry_mode_label(str(inferred.get("entry_outlook") or ""))
    return ""


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
            if _is_weak_manual_sell_hint(
                {"reason": reason, "side": side, "exit_kind": ek}
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
        append_exit_log(
            live_meta,
            symbol=symbol,
            reason=reason,
            is_auto=is_auto,
            order_uuid=uid,
        )
    if persist:
        try:
            from app.storage.persistence import save_live_meta

            save_live_meta(live_meta)
        except Exception:
            logger.debug("save_live_meta after order reason failed", exc_info=True)


def append_exit_log(
    live_meta: dict[str, Any],
    *,
    symbol: str,
    reason: str,
    is_auto: bool = True,
    order_uuid: str = "",
) -> None:
    """손/익절 매도 직전·직후 기록 — UUID 없어도 종목·시간으로 사후 매칭."""
    sym = str(symbol or "").upper()
    if not sym:
        return
    side_u = "SELL"
    exit_kind = classify_exit_kind(reason, side_u)
    if exit_kind not in ("tp", "sl"):
        return
    uid = str(order_uuid or "").strip()
    log = live_meta.setdefault("exit_log", [])
    if uid:
        for row in reversed(log):
            if not isinstance(row, dict):
                continue
            if str(row.get("order_uuid") or "") == uid:
                row["symbol"] = sym
                row["reason"] = reason
                row["is_auto"] = bool(is_auto)
                row["exit_kind"] = exit_kind
                live_meta["exit_log"] = log[-EXIT_LOG_KEEP:]
                return
    log.append(
        {
            "order_uuid": uid,
            "symbol": sym,
            "reason": reason,
            "is_auto": bool(is_auto),
            "side": side_u,
            "exit_kind": exit_kind,
            "ts": time.time(),
        }
    )
    live_meta["exit_log"] = log[-EXIT_LOG_KEEP:]


def link_exit_log_uuid(
    live_meta: dict[str, Any],
    *,
    symbol: str,
    reason: str,
    order_uuid: str,
) -> None:
    """매도 체결 UUID를 방금 기록한 exit_log에 연결."""
    sym = str(symbol or "").upper()
    uid = str(order_uuid or "").strip()
    if not sym or not uid:
        return
    log = live_meta.get("exit_log") or []
    now = time.time()
    for row in reversed(log):
        if not isinstance(row, dict):
            continue
        if str(row.get("symbol") or "").upper() != sym:
            continue
        if str(row.get("reason") or "") != reason:
            continue
        if str(row.get("order_uuid") or ""):
            continue
        if now - float(row.get("ts") or 0) > 900:
            continue
        row["order_uuid"] = uid
        return


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
    """GET /v1/orders?state=done — 페이지 수집 (429 시 재시도·부분 수집)."""
    by_uuid: dict[str, dict] = {}
    last_err: str | None = None
    rate_hit = False

    for page in range(1, max_pages + 1):
        batch: list[dict] | None = None
        for attempt in range(4):
            try:
                batch = await client.done_orders(limit=100, page=page)
                break
            except Exception as e:
                last_err = str(e)
                if _is_upbit_rate_limit(e) and attempt < 3:
                    rate_hit = True
                    await _wait_rate_limit(attempt, context=f"done_orders p{page}")
                    continue
                logger.warning("upbit done_orders page=%s: %s", page, e)
                batch = None
                break
        if batch is None:
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
        if rate_hit:
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
        batch: list[dict] | None = None
        for attempt in range(3):
            try:
                batch = await client.closed_orders(
                    start_time=start.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                    end_time=end.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                    limit=1000,
                    states=["done"],
                )
                break
            except Exception as e:
                if _is_upbit_rate_limit(e) and attempt < 2:
                    await _wait_rate_limit(attempt, context="closed_orders")
                    continue
                logger.warning("upbit closed_orders: %s", e)
                batch = None
                break
        if batch is None:
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
        except Exception as e:
            if _is_upbit_rate_limit(e):
                logger.warning("orders_by_uuids rate limited — skip enrich chunk")
                continue
            sem = asyncio.Semaphore(4)

            async def _one(u: str) -> None:
                async with sem:
                    for attempt in range(2):
                        try:
                            row = await client.get_order(u)
                            if row:
                                detail[u] = row
                            return
                        except Exception as ex:
                            if _is_upbit_rate_limit(ex) and attempt == 0:
                                await _wait_rate_limit(attempt, context="get_order")
                                continue
                            return

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


def _hint_from_exit_log(
    exit_log: list[Any],
    *,
    symbol: str,
    side: str,
    ts: float,
    window_sec: float = 300.0,
) -> dict[str, Any]:
    """업비트 UUID 힌트 없을 때 exit_log(손/익절) 시간·종목 매칭."""
    if str(side).upper() != "SELL" or not exit_log:
        return {}
    sym = symbol.upper()
    best: dict[str, Any] | None = None
    best_dt = window_sec + 1.0
    for row in exit_log:
        if not isinstance(row, dict):
            continue
        if str(row.get("symbol") or "").upper() != sym:
            continue
        if str(row.get("side") or "SELL").upper() != "SELL":
            continue
        row_ts = float(row.get("ts") or 0)
        if row_ts <= 0:
            continue
        dt = abs(row_ts - ts)
        if dt <= window_sec and dt < best_dt:
            best_dt = dt
            best = dict(row)
    return best or {}


def order_to_trade_dict(
    order: dict[str, Any],
    *,
    usdt_krw: float,
    reason_hints: dict[str, dict[str, Any]],
    exit_log: list[Any] | None = None,
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
    if _is_weak_manual_sell_hint(hint):
        hint = {}

    qty, funds, px_krw = _fill_from_order(order)
    if qty <= 1e-12:
        return None

    symbol = upbit_to_symbol(market).upper()
    ts = _parse_upbit_ts(order.get("created_at")) or time.time()

    if not hint and side == "SELL" and exit_log:
        hint = _hint_from_exit_log(
            exit_log, symbol=symbol, side=side, ts=ts
        )

    raw_reason = str(hint.get("reason") or "")
    is_auto = bool(hint.get("is_auto", False))
    has_hint = bool(hint)
    reason = normalize_trade_reason(
        side,
        raw_reason,
        is_auto=is_auto,
        has_aidi_hint=has_hint,
        exit_kind=str(hint.get("exit_kind") or ""),
    )

    m = coin_meta(symbol)
    rate = max(usdt_krw, 1.0)

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
    exit_log: list[Any] | None = None,
) -> list[TradeEvent]:
    cutoff = time.time() - UPBIT_TRADE_HISTORY_DAYS * 86400
    rows: list[dict[str, Any]] = []

    for order in orders:
        d = order_to_trade_dict(
            order,
            usdt_krw=usdt_krw,
            reason_hints=reason_hints,
            exit_log=exit_log,
        )
        if not d:
            continue
        ts = _f(d.get("ts"))
        if ts > 0 and ts < cutoff:
            continue
        rows.append(d)

    sem = asyncio.Semaphore(5)

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


def _relabel_trade_rows(
    live_meta: dict[str, Any],
    rows: list[dict[str, Any]],
    hints: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    exit_log = live_meta.get("exit_log") or []
    for row in rows:
        uid = str(row.get("order_uuid") or "")
        side_row = str(row.get("side") or "")
        hint_row = _order_reason_hint(live_meta, uid, side_row) or dict(
            hints.get(uid) or {}
        )
        if not _hint_applies_to_side(hint_row, side_row):
            hint_row = {}
        if _is_weak_manual_sell_hint(hint_row):
            hint_row = {}
        if not hint_row and side_row.upper() == "SELL":
            hint_row = _hint_from_exit_log(
                exit_log,
                symbol=str(row.get("symbol") or ""),
                side="SELL",
                ts=float(row.get("ts") or 0),
                window_sec=900.0,
            )
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
        has_hint = bool(hint_row)
        row["exit_kind"] = exit_kind
        row["reason"] = normalize_trade_reason(
            side_row,
            raw_reason,
            is_auto=bool(row.get("is_auto")),
            has_aidi_hint=has_hint,
            exit_kind=exit_kind,
        )
        if str(side_row).upper() == "SELL":
            if exit_kind in ("tp", "sl") and has_hint:
                row["is_auto"] = True
            if not str(row.get("entry_mode") or "").strip():
                row["entry_mode"] = resolve_sell_entry_mode(
                    live_meta,
                    symbol=str(row.get("symbol") or ""),
                    row=row,
                )
    return rows


def _trades_from_cached_meta(
    live_meta: dict[str, Any],
    *,
    usdt_krw: float,
    hints: dict[str, dict[str, Any]] | None = None,
) -> list[TradeEvent]:
    hints = hints or collect_reason_hints(live_meta)
    merged_rows = merge_trade_dicts(
        live_meta.get("trades") or [],
        usdt_krw=usdt_krw,
        limit=UPBIT_TRADE_LIMIT,
    )
    merged_rows = _relabel_trade_rows(live_meta, merged_rows, hints)
    live_meta["trades"] = merged_rows
    live_meta["trades_display_count"] = len(merged_rows)
    return merge_trade_events(merged_rows, usdt_krw=usdt_krw, limit=UPBIT_TRADE_LIMIT)


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

    last_sync = float(live_meta.get("trades_upbit_synced_at") or 0)
    if (
        not force
        and last_sync > 0
        and time.time() - last_sync < TRADES_SYNC_COOLDOWN_SEC
    ):
        logger.debug(
            "trades sync skipped (cooldown %.0fs / %ds)",
            time.time() - last_sync,
            TRADES_SYNC_COOLDOWN_SEC,
        )
        return _trades_from_cached_meta(live_meta, usdt_krw=usdt_krw, hints=hints)

    api_trades: list[TradeEvent] = []
    err_msg: str | None = None
    orders_fetched = 0
    max_pages = DONE_ORDER_MAX_PAGES if force else DONE_ORDER_MAX_PAGES_NORMAL

    try:
        orders = await fetch_done_orders_paginated(client, max_pages=max_pages)
        closed: list[dict] = []
        if force:
            closed = await _fetch_closed_orders(client)
        elif len(orders) < 80:
            closed = await _fetch_closed_orders(client, days=7)
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
            client,
            orders,
            usdt_krw=usdt_krw,
            reason_hints=hints,
            exit_log=live_meta.get("exit_log") or [],
        )
        live_meta["trades_orders_fetched"] = orders_fetched
        for t in api_trades:
            if t.order_uuid:
                remember_order_uuid(live_meta, t.order_uuid)
    except Exception as e:
        err_msg = str(e)[:220]
        if _is_upbit_rate_limit(e):
            logger.warning("upbit trades fetch rate limited: %s", err_msg)
        elif prev:
            logger.warning("upbit trades fetch failed (using cache): %s", err_msg)
        else:
            logger.exception("upbit trades fetch failed")

    combined = merge_trade_events(
        cached,
        [t.model_dump() for t in api_trades],
        usdt_krw=usdt_krw,
        limit=UPBIT_TRADE_LIMIT,
    )

    if not combined and prev:
        combined = prev

    if not combined and err_msg:
        live_meta["trades_sync_error"] = err_msg
    elif err_msg and not api_trades and prev:
        live_meta["trades_sync_error"] = (
            "업비트 요청 제한(429) — 마지막 저장 체결 내역을 표시 중 · "
            f"{TRADES_SYNC_COOLDOWN_SEC}초 후 자동 재조회"
            if _is_upbit_rate_limit(err_msg)
            else err_msg
        )
    elif not combined:
        live_meta["trades_sync_error"] = (
            "업비트 체결 주문이 없습니다. 최근 KRW 마켓 매매가 있는지 확인하세요."
        )
    else:
        live_meta.pop("trades_sync_error", None)

    if api_trades or not err_msg:
        live_meta["trades_upbit_synced_at"] = time.time()

    merged_rows = merge_trade_dicts(
        [t.model_dump() for t in combined],
        usdt_krw=usdt_krw,
        limit=UPBIT_TRADE_LIMIT,
    )
    merged_rows = _relabel_trade_rows(live_meta, merged_rows, hints)
    live_meta["trades"] = merged_rows
    live_meta["trades_display_count"] = len(merged_rows)
    return merge_trade_events(merged_rows, usdt_krw=usdt_krw, limit=UPBIT_TRADE_LIMIT)

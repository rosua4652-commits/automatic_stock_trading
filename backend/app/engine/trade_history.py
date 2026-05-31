"""체결 내역 병합 — sync 시 in-memory 매도 기록 유실 방지."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.market.coin_registry import coin_meta
from app.market.upbit_order_fill import repair_trade_dict, resolve_upbit_fill
from app.models import TradeEvent

if TYPE_CHECKING:
    from app.market.upbit_client import UpbitClient


def trade_fingerprint(t: dict[str, Any]) -> tuple:
    return (
        round(float(t.get("ts") or 0), 2),
        str(t.get("symbol") or "").upper(),
        str(t.get("side") or "").upper(),
        round(float(t.get("quantity") or 0), 6),
        round(float(t.get("amount_krw") or 0), 0),
        str(t.get("reason") or "")[:48],
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
    limit: int = 100,
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
    limit: int = 100,
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
        return float(raw)
    text = str(raw).strip()
    if not text:
        return 0.0
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return 0.0


def _known_order_uuids(live_meta: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for uid in live_meta.get("recorded_order_uuids") or []:
        if uid:
            out.add(str(uid))
    for pm in (live_meta.get("positions_meta") or {}).values():
        if not isinstance(pm, dict):
            continue
        pe = pm.get("pending_exit")
        if isinstance(pe, dict) and pe.get("order_uuid"):
            out.add(str(pe["order_uuid"]))
    return out


def remember_order_uuid(live_meta: dict[str, Any], uuid: str) -> None:
    uid = str(uuid or "").strip()
    if not uid:
        return
    rows = [str(x) for x in (live_meta.get("recorded_order_uuids") or []) if x]
    if uid not in rows:
        rows.append(uid)
    live_meta["recorded_order_uuids"] = rows[-200:]


def _existing_fingerprints(
    portfolio,
    live_meta: dict[str, Any],
    *,
    usdt_krw: float,
) -> set[tuple]:
    fps: set[tuple] = set()
    for src in (portfolio.trades, live_meta.get("trades") or []):
        for raw in src:
            d = repair_trade_dict(_as_dict(raw), usdt_krw=usdt_krw)
            if str(d.get("side") or "").upper() == "SELL":
                fps.add(trade_fingerprint(d))
    return fps


def _qty_drops(
    prev_qty: dict[str, float],
    new_qty: dict[str, float],
) -> list[tuple[str, float]]:
    drops: list[tuple[str, float]] = []
    symbols = set(prev_qty) | set(new_qty)
    for sym in symbols:
        before = float(prev_qty.get(sym) or 0)
        after = float(new_qty.get(sym) or 0)
        delta = before - after
        if delta > 1e-8:
            drops.append((sym.upper(), delta))
    return drops


async def backfill_recent_sells(
    portfolio,
    live_meta: dict[str, Any],
    client: "UpbitClient",
    *,
    prev_qty: dict[str, float],
    new_qty: dict[str, float],
    markets_by_symbol: dict[str, str],
    pending_reasons: dict[str, str] | None = None,
) -> int:
    """
    업비트 done 매도 주문에서 AIDI에 없는 SELL 체결을 보충.
    지정가 대기·앱 재시작·sync race 로 누락된 익절/매도 기록 복구.
    """
    drops = _qty_drops(prev_qty, new_qty)
    if not drops:
        live_meta["last_holdings_qty"] = {
            sym: float(qty) for sym, qty in new_qty.items() if qty > 1e-12
        }
        return 0

    rate = max(float(getattr(portfolio, "usdt_krw", 0) or 0), 1.0)
    known_uuids = _known_order_uuids(live_meta)
    existing = _existing_fingerprints(portfolio, live_meta, usdt_krw=rate)
    pending = pending_reasons or {}
    added = 0

    for sym, delta_qty in drops:
        market = markets_by_symbol.get(sym)
        if not market:
            continue
        try:
            orders = await client.done_orders(market=market, limit=40)
        except Exception:
            continue

        reason_hint = pending.get(sym) or "매도(동기화)"
        matched_qty = 0.0

        for order in orders:
            if str(order.get("side") or "").lower() != "ask":
                continue
            uid = str(order.get("uuid") or "")
            if uid and uid in known_uuids:
                raw_qty = float(order.get("executed_volume") or 0)
                matched_qty += raw_qty
                continue

            try:
                qty, funds, px_krw = await resolve_upbit_fill(
                    client,
                    order,
                    fallback_qty=float(order.get("executed_volume") or 0),
                )
            except Exception:
                qty, funds, px_krw = 0.0, 0.0, 0.0

            if qty <= 1e-12:
                continue

            ts = _parse_upbit_ts(order.get("created_at")) or time.time()
            m = coin_meta(sym)
            row = repair_trade_dict(
                {
                    "ts": ts,
                    "symbol": sym,
                    "base": m["base"],
                    "display": m["display"],
                    "side": "SELL",
                    "price": px_krw / rate if px_krw > 0 else 0.0,
                    "price_krw": round(px_krw, 4) if px_krw > 0 else 0.0,
                    "quantity": qty,
                    "amount_krw": round(funds, 0) if funds > 0 else 0.0,
                    "amount_usdt": round(funds / rate, 4) if funds > 0 else 0.0,
                    "reason": reason_hint,
                    "is_auto": "익절" in reason_hint or "손절" in reason_hint,
                },
                usdt_krw=rate,
            )
            fp = trade_fingerprint(row)
            if fp in existing:
                if uid:
                    remember_order_uuid(live_meta, uid)
                    known_uuids.add(uid)
                matched_qty += qty
                continue

            portfolio.trades.append(TradeEvent(**row))
            existing.add(fp)
            matched_qty += qty
            added += 1
            if uid:
                remember_order_uuid(live_meta, uid)
                known_uuids.add(uid)

            if matched_qty >= delta_qty * 0.95:
                break

    live_meta["last_holdings_qty"] = {
        sym: float(qty) for sym, qty in new_qty.items() if qty > 1e-12
    }
    if added:
        portfolio.trades = merge_trade_events(
            portfolio.trades,
            live_meta.get("trades", [])[-100:],
            usdt_krw=rate,
            limit=100,
        )
    return added

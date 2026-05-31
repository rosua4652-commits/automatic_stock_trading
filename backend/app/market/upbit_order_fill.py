"""업비트 주문 체결 정보 파싱 (금액·수량·단가)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.market.upbit_client import UpbitClient


def order_executed_qty(order: dict[str, Any]) -> float:
    try:
        return float(order.get("executed_volume") or 0)
    except (TypeError, ValueError):
        return 0.0


def parse_upbit_order_fill(
    order: dict[str, Any],
    *,
    amount_krw_hint: float = 0.0,
    price_krw_hint: float = 0.0,
) -> tuple[float, float, float]:
    """
    Returns: (executed_qty, amount_krw, price_krw)
    """
    trades = order.get("trades") or []
    if trades:
        qty = sum(float(t.get("volume") or 0) for t in trades)
        funds = sum(float(t.get("funds") or 0) for t in trades)
        if qty > 1e-12 and funds > 0:
            return qty, funds, funds / qty

    qty = order_executed_qty(order)
    if qty > 1e-12:
        if amount_krw_hint > 0:
            return qty, amount_krw_hint, amount_krw_hint / qty
        if price_krw_hint > 0:
            return qty, qty * price_krw_hint, price_krw_hint

    if amount_krw_hint > 0 and price_krw_hint > 0:
        return amount_krw_hint / price_krw_hint, amount_krw_hint, price_krw_hint

    return 0.0, 0.0, 0.0


async def resolve_upbit_fill(
    client: "UpbitClient",
    order: dict[str, Any],
    *,
    amount_krw_hint: float = 0.0,
    price_krw_hint: float = 0.0,
    fallback_qty: float = 0.0,
) -> tuple[float, float, float]:
    """주문 UUID 재조회 + 힌트/의도수량으로 체결 정보 보완."""
    uid = order.get("uuid")
    if uid:
        try:
            order = await client.get_order(str(uid))
        except Exception:
            pass

    raw_qty = order_executed_qty(order)
    parsed_qty, funds, px = parse_upbit_order_fill(
        order,
        amount_krw_hint=amount_krw_hint,
        price_krw_hint=price_krw_hint,
    )

    qty = parsed_qty if parsed_qty > 1e-12 else raw_qty
    if qty <= 1e-12:
        qty = max(float(fallback_qty), 0.0)

    if funds <= 0 and px > 0 and qty > 0:
        funds = qty * px
    elif funds <= 0 and price_krw_hint > 0 and qty > 0:
        px = price_krw_hint
        funds = qty * px
    elif funds <= 0 and amount_krw_hint > 0 and qty > 0:
        funds = amount_krw_hint
        px = funds / qty

    if px <= 0 and qty > 0 and funds > 0:
        px = funds / qty

    return qty, funds, px


def repair_trade_dict(t: dict[str, Any], *, usdt_krw: float = 1350.0) -> dict[str, Any]:
    """저장된 체결 내역 누락 필드 보완 (옛 데이터·렉 시)."""
    out = dict(t)
    rate = max(float(usdt_krw), 1.0)
    q = float(out.get("quantity") or 0)
    amt = float(out.get("amount_krw") or 0)
    px_krw = float(out.get("price_krw") or 0)
    px = float(out.get("price") or 0)

    if px_krw <= 0 and px > 0:
        px_krw = px * rate
    if px_krw <= 0 and q > 1e-12 and amt > 0:
        px_krw = amt / q
    if amt <= 0 and q > 1e-12 and px_krw > 0:
        amt = q * px_krw
    elif amt <= 0 and q > 1e-12 and px > 0:
        amt = q * px * rate
        if px_krw <= 0:
            px_krw = px * rate
    if q <= 1e-12 and amt > 0 and px_krw > 0:
        q = amt / px_krw
    if px <= 0 and px_krw > 0:
        px = px_krw / rate

    if px_krw > 0:
        out["price_krw"] = round(px_krw, 4)
    if q > 0:
        out["quantity"] = q
    if amt > 0:
        out["amount_krw"] = round(amt, 0)
    if px > 0:
        out["price"] = px
    return out

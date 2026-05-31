"""업비트 주문 체결 정보 파싱 (금액·수량·단가)."""

from __future__ import annotations

from typing import Any


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

    qty = float(order.get("executed_volume") or 0)
    if qty > 1e-12:
        if amount_krw_hint > 0:
            return qty, amount_krw_hint, amount_krw_hint / qty
        if price_krw_hint > 0:
            return qty, qty * price_krw_hint, price_krw_hint

    paid = float(order.get("paid_fee") or 0)
    if amount_krw_hint > 0 and qty <= 0:
        px = price_krw_hint if price_krw_hint > 0 else 0.0
        if px > 0:
            return amount_krw_hint / px, amount_krw_hint, px

    _ = paid
    return 0.0, 0.0, 0.0

"""체결 파싱·복구 테스트."""

import asyncio

from app.market.upbit_order_fill import (
    parse_upbit_order_fill,
    repair_trade_dict,
    resolve_upbit_fill,
)


class _FakeClient:
    def __init__(self, order: dict):
        self._order = order

    async def get_order(self, uuid: str) -> dict:
        return self._order


def test_resolve_keeps_executed_volume_when_trades_empty():
    order = {"uuid": "abc", "executed_volume": "12.5", "trades": []}
    client = _FakeClient(
        {
            "uuid": "abc",
            "executed_volume": "12.5",
            "trades": [{"volume": "12.5", "funds": "1250"}],
        }
    )
    qty, funds, px = asyncio.run(
        resolve_upbit_fill(
            client, order, price_krw_hint=100.0, fallback_qty=12.5
        )
    )
    assert qty == 12.5
    assert funds == 1250
    assert px == 100


def test_parse_does_not_zero_when_hint_available():
    order = {"executed_volume": "10"}
    qty, funds, px = parse_upbit_order_fill(order, price_krw_hint=105.0)
    assert qty == 10
    assert funds == 1050
    assert px == 105


def test_repair_trade_from_price_only():
    fixed = repair_trade_dict(
        {
            "side": "SELL",
            "reason": "익절",
            "price": 0.5,
            "quantity": 0,
            "amount_krw": 0,
        },
        usdt_krw=1000.0,
    )
    assert fixed["price_krw"] == 500.0
    # still missing qty/amt without more hints

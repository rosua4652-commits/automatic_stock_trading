"""체결 내역 — 업비트 API 로드 테스트."""

import asyncio
import time

from app.engine.trade_history import (
    fetch_done_orders_paginated,
    load_trades_from_upbit,
    merge_trade_dicts,
    merge_trade_events,
    order_to_trade_dict,
    remember_order_reason,
    trade_fingerprint,
)
from app.models import TradeEvent


class _FakeUpbitClient:
    def __init__(self, pages: list[list[dict]], details: dict[str, dict] | None = None):
        self._pages = pages
        self._details = details or {}

    async def done_orders(self, market=None, *, limit=50, page=1):
        idx = page - 1
        if idx < len(self._pages):
            return self._pages[idx]
        return []

    async def closed_orders(self, **kwargs):
        return []

    async def orders_by_uuids(self, uuids: list[str]):
        return [self._details[u] for u in uuids if u in self._details]

    async def get_order(self, uuid: str):
        return self._details.get(uuid, {})


def test_merge_trade_dicts_keeps_both_sources():
    mem = [
        {
            "ts": 100.0,
            "symbol": "ARBUSDT",
            "side": "SELL",
            "quantity": 10,
            "amount_krw": 5000,
            "reason": "익절",
            "price": 0.5,
            "order_uuid": "sell-1",
        }
    ]
    disk = [
        {
            "ts": 90.0,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 0.01,
            "amount_krw": 100000,
            "reason": "업비트 매수",
            "price": 70000,
            "order_uuid": "buy-1",
        }
    ]
    merged = merge_trade_dicts(mem, disk, usdt_krw=1350.0, limit=100)
    assert len(merged) == 2
    assert trade_fingerprint(merged[0])[0] == "uuid"


def test_fetch_done_orders_paginated():
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S+09:00", time.localtime())
    pages = [
        [
            {
                "uuid": "1",
                "market": "KRW-BTC",
                "side": "bid",
                "ord_type": "price",
                "executed_volume": "0.001",
                "price": "100000",
                "created_at": now_iso,
            }
        ],
        [],
    ]
    client = _FakeUpbitClient(pages)
    orders = asyncio.run(fetch_done_orders_paginated(client))
    assert len(orders) == 1
    assert orders[0]["uuid"] == "1"


def test_order_to_trade_market_buy():
    row = order_to_trade_dict(
        {
            "uuid": "b1",
            "market": "KRW-ARB",
            "side": "bid",
            "ord_type": "price",
            "executed_volume": "10",
            "price": "50000",
            "created_at": "2026-03-30T12:00:00+09:00",
        },
        usdt_krw=1350.0,
        reason_hints={},
    )
    assert row is not None
    assert row["side"] == "BUY"
    assert row["amount_krw"] == 50000


def test_load_trades_from_upbit_includes_sells():
    live_meta: dict = {"order_reasons": {}}
    remember_order_reason(
        live_meta, "sell-uuid-1", reason="익절", is_auto=True
    )
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S+09:00", time.localtime())
    list_order = {
        "uuid": "sell-uuid-1",
        "market": "KRW-ARB",
        "side": "ask",
        "ord_type": "market",
        "executed_volume": "12.5",
        "created_at": now_iso,
    }
    detail = {
        "uuid": "sell-uuid-1",
        "market": "KRW-ARB",
        "side": "ask",
        "executed_volume": "12.5",
        "created_at": now_iso,
        "trades": [{"volume": "12.5", "funds": "12500"}],
    }
    client = _FakeUpbitClient([[list_order]], {"sell-uuid-1": detail})

    trades = asyncio.run(
        load_trades_from_upbit(
            client, live_meta, usdt_krw=1350.0, force=True
        )
    )
    assert len(trades) == 1
    assert trades[0].side == "SELL"
    assert trades[0].amount_krw == 12500
    assert trades[0].reason == "익절"

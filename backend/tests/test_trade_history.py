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
)
from app.models import TradeEvent


class _FakeUpbitClient:
    def __init__(
        self,
        pages: list[list[dict]],
        details: dict[str, dict] | None = None,
        closed: list[dict] | None = None,
    ):
        self._pages = pages
        self._details = details or {}
        self._closed = closed or []

    async def done_orders(self, market=None, *, limit=50, page=1):
        idx = page - 1
        if idx < len(self._pages):
            return self._pages[idx]
        return []

    async def closed_orders(self, **kwargs):
        return self._closed

    async def orders_by_uuids(self, uuids: list[str]):
        return [self._details[u] for u in uuids if u in self._details]

    async def get_order(self, uuid: str):
        return self._details.get(uuid, {})


def test_fetch_done_orders_no_early_break():
    """executed_volume=0 행만 있어도 다음 페이지를 보지 않고, KRW 주문은 수집."""
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S+09:00", time.localtime())
    pages = [
        [
            {
                "uuid": "old",
                "market": "KRW-ETH",
                "side": "bid",
                "executed_volume": "0",
                "created_at": "2020-01-01T00:00:00+09:00",
            },
            {
                "uuid": "new",
                "market": "KRW-BTC",
                "side": "bid",
                "ord_type": "price",
                "executed_volume": "0.001",
                "price": "100000",
                "created_at": now_iso,
            },
        ],
    ]
    client = _FakeUpbitClient(pages)
    orders = asyncio.run(fetch_done_orders_paginated(client))
    assert len(orders) == 2


def test_order_to_trade_market_buy():
    row = order_to_trade_dict(
        {
            "uuid": "b1",
            "market": "KRW-ARB",
            "side": "bid",
            "ord_type": "price",
            "executed_volume": "10",
            "price": "50000",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00", time.localtime()),
        },
        usdt_krw=1350.0,
        reason_hints={},
    )
    assert row is not None
    assert row["side"] == "BUY"
    assert row["amount_krw"] == 50000


def test_load_trades_keeps_cached_when_api_empty():
    cached_evt = {
        "ts": time.time(),
        "symbol": "BTCUSDT",
        "base": "BTC",
        "display": "BTC/KRW",
        "side": "BUY",
        "price": 90000,
        "price_krw": 90000000,
        "quantity": 0.001,
        "amount_krw": 90000,
        "amount_usdt": 66.6,
        "reason": "수동 매수",
        "is_auto": False,
        "order_uuid": "local-1",
    }
    live_meta = {"trades": [cached_evt], "order_reasons": {}}
    client = _FakeUpbitClient([[]])

    trades = asyncio.run(
        load_trades_from_upbit(client, live_meta, usdt_krw=1350.0, force=True)
    )
    assert len(trades) == 1
    assert trades[0].side == "BUY"
    assert trades[0].amount_krw == 90000


def test_load_trades_from_upbit_includes_sells():
    live_meta: dict = {"order_reasons": {}, "trades": []}
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
        **list_order,
        "trades": [{"volume": "12.5", "funds": "12500"}],
    }
    client = _FakeUpbitClient([[list_order]], {"sell-uuid-1": detail})

    trades = asyncio.run(
        load_trades_from_upbit(client, live_meta, usdt_krw=1350.0, force=True)
    )
    assert len(trades) == 1
    assert trades[0].side == "SELL"
    assert trades[0].amount_krw == 12500

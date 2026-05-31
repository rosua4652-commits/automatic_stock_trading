"""체결 내역 — 업비트 API 로드 테스트."""

import asyncio
import time

from app.engine.trade_history import (
    TRADES_SYNC_COOLDOWN_SEC,
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


class _FailIfCalledClient(_FakeUpbitClient):
    async def done_orders(self, market=None, *, limit=50, page=1):
        raise RuntimeError('Upbit: {"name":"too_many_requests"}')


def test_load_trades_cooldown_skips_upbit_api():
    cached_evt = {
        "ts": time.time(),
        "symbol": "BTCUSDT",
        "base": "BTC",
        "display": "BTC/KRW",
        "side": "BUY",
        "price": 1.0,
        "price_krw": 1000,
        "quantity": 1.0,
        "amount_krw": 1000,
        "amount_usdt": 1.0,
        "reason": "수동 매수",
        "is_auto": False,
        "order_uuid": "cool-1",
    }
    live_meta = {
        "trades": [cached_evt],
        "trades_upbit_synced_at": time.time(),
        "order_reasons": {},
    }
    client = _FailIfCalledClient([[]])

    trades = asyncio.run(
        load_trades_from_upbit(client, live_meta, usdt_krw=1350.0, force=False)
    )
    assert len(trades) == 1
    assert trades[0].order_uuid == "cool-1"


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
    assert trades[0].reason == "익절"


def test_export_live_meta_preserves_order_reasons():
    from app.engine.live_sync import export_live_meta
    from app.engine.portfolio import PortfolioManager

    prev = {
        "order_reasons": {
            "u1": {
                "reason": "손절",
                "is_auto": True,
                "side": "SELL",
                "exit_kind": "sl",
            }
        }
    }
    out = export_live_meta(PortfolioManager(), preserve=prev)
    assert out["order_reasons"]["u1"]["reason"] == "손절"


def test_stale_cached_manual_sell_relabeled_from_order_reasons():
    live_meta: dict = {
        "order_reasons": {
            "sell-uuid-1": {
                "reason": "익절",
                "is_auto": True,
                "side": "SELL",
                "exit_kind": "tp",
            }
        },
        "trades": [
            {
                "ts": time.time(),
                "symbol": "ARBUSDT",
                "base": "ARB",
                "display": "ARB/KRW",
                "side": "SELL",
                "price": 1.0,
                "price_krw": 1000,
                "quantity": 12.5,
                "amount_krw": 12500,
                "amount_usdt": 9.2,
                "reason": "수동 매도",
                "is_auto": True,
                "order_uuid": "sell-uuid-1",
            }
        ],
    }
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
    assert trades[0].reason == "익절"

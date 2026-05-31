"""체결 내역 — 업비트 API 로드 테스트."""

import asyncio
import time

from app.engine.trade_history import (
    load_trades_from_upbit,
    merge_trade_dicts,
    merge_trade_events,
    remember_order_reason,
    trade_fingerprint,
)
from app.models import TradeEvent


class _FakeUpbitClient:
    def __init__(self, orders: list[dict], details: dict[str, dict] | None = None):
        self._orders = orders
        self._details = details or {}

    async def closed_orders(self, **kwargs):
        return list(self._orders)

    async def done_orders(self, market=None, *, limit=50, page=1):
        return list(self._orders)

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


def test_merge_trade_events_survives_sync_race():
    in_mem = [
        TradeEvent(
            ts=time.time(),
            symbol="ZKPUSDT",
            base="ZKP",
            display="ZKP/KRW",
            side="SELL",
            price=0.08,
            price_krw=104.0,
            quantity=480.0,
            amount_krw=49920,
            amount_usdt=36.9,
            reason="익절",
            is_auto=True,
            order_uuid="uuid-sell",
        )
    ]
    meta = [
        {
            "ts": time.time() - 60,
            "symbol": "ZKPUSDT",
            "base": "ZKP",
            "display": "ZKP/KRW",
            "side": "BUY",
            "price": 0.077,
            "price_krw": 104.0,
            "quantity": 480.0,
            "amount_krw": 49920,
            "amount_usdt": 36.9,
            "reason": "업비트 매수",
            "is_auto": False,
            "order_uuid": "uuid-buy",
        }
    ]
    out = merge_trade_events(in_mem, meta, usdt_krw=1350.0, limit=100)
    sides = {t.side for t in out}
    assert sides == {"BUY", "SELL"}


def test_load_trades_from_upbit_includes_sells():
    live_meta: dict = {"order_reasons": {}}
    remember_order_reason(
        live_meta, "sell-uuid-1", reason="익절", is_auto=True
    )
    list_order = {
        "uuid": "sell-uuid-1",
        "market": "KRW-ARB",
        "side": "ask",
        "ord_type": "market",
        "executed_volume": "12.5",
        "created_at": "2026-03-30T12:00:00+09:00",
    }
    detail = {
        "uuid": "sell-uuid-1",
        "market": "KRW-ARB",
        "side": "ask",
        "executed_volume": "12.5",
        "created_at": "2026-03-30T12:00:00+09:00",
        "trades": [{"volume": "12.5", "funds": "12500"}],
    }
    client = _FakeUpbitClient([list_order], {"sell-uuid-1": detail})

    trades = asyncio.run(
        load_trades_from_upbit(
            client, live_meta, usdt_krw=1350.0, force=True
        )
    )
    assert len(trades) == 1
    assert trades[0].side == "SELL"
    assert trades[0].amount_krw == 12500
    assert trades[0].reason == "익절"
    assert live_meta.get("trades_upbit_synced_at")


def test_load_trades_uses_cache_when_recent():
    live_meta = {
        "trades_upbit_synced_at": time.time(),
        "trades": [
            {
                "ts": 1.0,
                "symbol": "BTCUSDT",
                "base": "BTC",
                "display": "BTC/KRW",
                "side": "SELL",
                "price": 90000000,
                "price_krw": 90000000,
                "quantity": 0.001,
                "amount_krw": 90000,
                "amount_usdt": 66.6,
                "reason": "업비트 매도",
                "is_auto": False,
                "order_uuid": "cached-1",
            }
        ],
    }
    client = _FakeUpbitClient([])

    trades = asyncio.run(
        load_trades_from_upbit(client, live_meta, usdt_krw=1350.0, force=False)
    )
    assert len(trades) == 1
    assert trades[0].order_uuid == "cached-1"

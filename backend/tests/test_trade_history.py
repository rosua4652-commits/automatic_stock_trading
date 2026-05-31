"""체결 내역 병합·백필 테스트."""

import asyncio
import time

from app.engine.trade_history import (
    backfill_recent_sells,
    merge_trade_dicts,
    merge_trade_events,
    trade_fingerprint,
)
from app.engine.portfolio import PortfolioManager
from app.models import TradeEvent


class _FakeUpbitClient:
    def __init__(self, orders: list[dict]):
        self._orders = orders

    async def done_orders(self, market: str | None = None, *, limit: int = 50):
        if market:
            return [o for o in self._orders if o.get("market") == market]
        return self._orders


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
        }
    ]
    disk = [
        {
            "ts": 90.0,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 0.01,
            "amount_krw": 100000,
            "reason": "수동 매수",
            "price": 70000,
        }
    ]
    merged = merge_trade_dicts(mem, disk, usdt_krw=1350.0, limit=100)
    fps = {trade_fingerprint(row) for row in merged}
    assert len(merged) == 2
    assert trade_fingerprint(merge_trade_dicts(mem, [], limit=1)[0]) in fps


def test_merge_trade_events_survives_sync_race():
    """sync가 meta만 읽을 때 in-memory 매도가 사라지지 않음."""
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
            "reason": "수동 매수",
            "is_auto": False,
        }
    ]
    out = merge_trade_events(in_mem, meta, usdt_krw=1350.0, limit=100)
    sides = {t.side for t in out}
    assert sides == {"BUY", "SELL"}


def test_backfill_adds_missing_sell():
    portfolio = PortfolioManager()
    portfolio.usdt_krw = 1350.0
    live_meta: dict = {"recorded_order_uuids": [], "trades": []}
    order = {
        "uuid": "sell-uuid-1",
        "market": "KRW-ARB",
        "side": "ask",
        "executed_volume": "12.5",
        "created_at": "2026-03-30T12:00:00+09:00",
        "trades": [{"volume": "12.5", "funds": "12500"}],
    }
    client = _FakeUpbitClient([order])

    added = asyncio.run(
        backfill_recent_sells(
            portfolio,
            live_meta,
            client,
            prev_qty={"ARBUSDT": 12.5},
            new_qty={},
            markets_by_symbol={"ARBUSDT": "KRW-ARB"},
            pending_reasons={"ARBUSDT": "익절"},
        )
    )
    assert added == 1
    assert len(portfolio.trades) == 1
    assert portfolio.trades[0].side == "SELL"
    assert portfolio.trades[0].amount_krw == 12500
    assert "sell-uuid-1" in live_meta["recorded_order_uuids"]

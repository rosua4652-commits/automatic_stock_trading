"""실거래 포지션 메타 — 롱/AI 동기화 복구."""

from app.engine.live_position_meta import (
    heal_position_meta,
    infer_recent_aidi_buy,
    outlook_from_reason_text,
    patch_position_meta_for_buy,
)


def test_outlook_from_auto_invest_reason():
    assert outlook_from_reason_text("AI 자동투자 · 5,000원") == "AI 롱 자동"
    assert outlook_from_reason_text("AI 단타 자동 · 익절") == "AI 단타 자동"


def test_patch_then_heal_restores_auto_qty():
    live_meta: dict = {
        "positions_meta": {},
        "trades": [
            {
                "ts": 100.0,
                "symbol": "KITEUSDT",
                "side": "BUY",
                "reason": "승인 매수",
                "is_auto": True,
                "order_uuid": "u1",
                "amount_krw": 5000,
            }
        ],
        "order_reasons": {
            "u1": {
                "reason": "AI 자동투자 · 5,000원 · AI 롱 자동",
                "is_auto": True,
                "side": "BUY",
            }
        },
    }
    patch_position_meta_for_buy(
        live_meta,
        "KITEUSDT",
        add_qty=10.0,
        amount_krw=5000,
        entry_outlook="AI 롱 자동",
        entry_reason="차트 적합",
        as_auto=True,
    )
    pm = heal_position_meta(
        {"auto_quantity": 0, "entry_reason": "업비트 동기화"},
        "KITEUSDT",
        live_meta,
        total_qty=10.0,
    )
    assert pm["auto_quantity"] == 10.0
    assert pm["entry_outlook"] == "AI 롱 자동"
    assert "업비트 동기화" not in pm["entry_reason"]


def test_infer_recent_aidi_buy():
    live_meta = {
        "trades": [],
        "order_reasons": {
            "x": {
                "reason": "AI 자동투자 · 롱",
                "is_auto": True,
                "side": "BUY",
            }
        },
    }
    assert infer_recent_aidi_buy(live_meta, "ABC") is None

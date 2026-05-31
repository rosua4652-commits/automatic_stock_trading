"""매매 사유 라벨."""

from app.engine.trade_history import normalize_trade_reason


def test_normalize_upbit_only_sell():
    assert (
        normalize_trade_reason("SELL", "", has_aidi_hint=False)
        == "수동 매도"
    )


def test_normalize_tp_sl():
    assert normalize_trade_reason("SELL", "익절", has_aidi_hint=True) == "익절"
    assert normalize_trade_reason("SELL", "손절", has_aidi_hint=True) == "손절"
    assert (
        normalize_trade_reason("SELL", "급락 방어", has_aidi_hint=True)
        == "손절"
    )


def test_normalize_manual_buy():
    assert (
        normalize_trade_reason(
            "BUY", "수동 매수 · 50000원", has_aidi_hint=True
        )
        == "수동 매수"
    )


def test_normalize_approval_buy():
    assert (
        normalize_trade_reason(
            "BUY", "AI 승인 · 50000원", is_auto=True, has_aidi_hint=True
        )
        == "승인 매수"
    )

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


def test_buy_never_labeled_tp_sl():
    """매수에는 익절/손절 라벨 금지 (잘못된 UUID 힌트 보정)."""
    assert (
        normalize_trade_reason(
            "BUY", "익절", has_aidi_hint=True, exit_kind="tp"
        )
        == "수동 매수"
    )
    assert (
        normalize_trade_reason(
            "BUY", "손절", has_aidi_hint=True, exit_kind="sl"
        )
        == "수동 매수"
    )


def test_normalize_sl_tp_with_exit_kind_not_auto():
    """전량 손익절 매도(is_auto=False)도 exit_kind·사유로 익절/손절 표기."""
    assert (
        normalize_trade_reason(
            "SELL",
            "익절",
            is_auto=False,
            has_aidi_hint=True,
            exit_kind="tp",
        )
        == "익절"
    )
    assert (
        normalize_trade_reason(
            "SELL",
            "",
            is_auto=False,
            has_aidi_hint=True,
            exit_kind="sl",
        )
        == "손절"
    )

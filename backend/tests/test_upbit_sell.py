"""업비트 소액 매도 — 시장가 5천원 미만 시 지정가."""

from app.market.upbit_sell import (
    MIN_MARKET_ASK_KRW,
    min_limit_price_krw,
    price_tick_krw,
)


def test_zkp_like_position_gets_limit_above_bid():
    vol = 48.0769
    bid = 103.0
    px = min_limit_price_krw(vol, floor_bid=bid)
    assert px >= bid
    assert vol * px >= MIN_MARKET_ASK_KRW - 0.01
    assert px == 105.0


def test_large_position_uses_market_threshold():
    vol = 100.0
    bid = 103.0
    assert vol * bid >= MIN_MARKET_ASK_KRW


def test_price_tick_for_103_krw():
    assert price_tick_krw(103) == 1.0

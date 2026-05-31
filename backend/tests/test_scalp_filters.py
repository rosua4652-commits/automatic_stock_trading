from app.engine.scalp_filters import scalp_market_fit


def test_scalp_rejects_low_volume_and_flat():
    ok, why = scalp_market_fit(
        volume_usdt=500_000,
        change_24h=0.5,
        min_volume_usdt=2_000_000,
        min_abs_change_24h=2.0,
    )
    assert not ok
    assert "거래대금" in why
    assert "변동" in why


def test_scalp_accepts_liquid_volatile():
    ok, why = scalp_market_fit(
        volume_usdt=5_000_000,
        change_24h=-3.2,
        min_volume_usdt=2_000_000,
        min_abs_change_24h=2.0,
    )
    assert ok
    assert why == ""

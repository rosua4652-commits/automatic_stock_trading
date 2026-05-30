"""Regression: loop variable must not shadow upbit_feed import."""


def test_sync_upbit_no_market_local_shadow():
    path = __file__.replace("test_live_sync_shadow.py", "../app/engine/live_sync.py")
    text = open(path, encoding="utf-8").read()
    assert "from app.market.upbit_data import market as upbit_feed" in text
    assert "await upbit_feed.usdt_krw_rate()" in text
    assert "        market = f\"KRW-{cur}\"" not in text
    assert "krw_market = f\"KRW-{cur}\"" in text

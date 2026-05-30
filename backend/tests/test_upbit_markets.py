from app.market.upbit_client import symbol_to_upbit
from app.market.upbit_markets import resolve_upbit_market


def test_resolve_upbit_market_listed():
    markets = {"KRW-BTC", "KRW-ETH", "KRW-XRP"}
    assert resolve_upbit_market("BTCUSDT", markets) == "KRW-BTC"
    assert resolve_upbit_market("ETHUSDT", markets) is not None


def test_resolve_upbit_market_binance_only():
    markets = {"KRW-BTC", "KRW-ETH"}
    assert resolve_upbit_market("BROCCOLI714USDT", markets) is None
    assert symbol_to_upbit("BROCCOLI714USDT") == "KRW-BROCCOLI714"

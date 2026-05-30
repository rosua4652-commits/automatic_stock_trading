"""캔들 429 시 예외 없이 빈/캐시 반환."""

from app.market import upbit_data as ud


def test_get_cached_klines_missing():
    assert ud.upbit_data.get_cached_klines("NOPEUSDT", "1h") is None

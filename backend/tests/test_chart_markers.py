from app.engine.chart_markers import align_chart_markers, snap_trade_time_to_candles


def test_snap_trade_time_to_candles():
    times = [1000, 1060, 1120]
    assert snap_trade_time_to_candles(1050, times) == 1000
    assert snap_trade_time_to_candles(1120, times) == 1120
    assert snap_trade_time_to_candles(999, times) == 1000


def test_align_chart_markers_snaps_to_candle():
    candles = [{"time": 3600}, {"time": 7200}]
    markers = [{"time": 3650, "price": 1.0, "side": "BUY", "text": "매수"}]
    out = align_chart_markers(markers, candles)
    assert len(out) == 1
    assert out[0]["time"] == 3600

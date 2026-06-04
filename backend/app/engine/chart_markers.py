"""차트 매매 마커 — lightweight-charts 봉 시간에 맞춤."""

from __future__ import annotations


def snap_trade_time_to_candles(trade_ts: int, candle_times: list[int]) -> int:
    """거래 시각을 해당 구간 봉 open time(초)으로 내림 스냅."""
    if not candle_times:
        return trade_ts
    ts = int(trade_ts)
    if ts in candle_times:
        return ts
    best: int | None = None
    for t in candle_times:
        if t <= ts:
            best = t
        else:
            break
    return best if best is not None else candle_times[0]


def align_chart_markers(
    markers: list[dict],
    candles: list[dict],
) -> list[dict]:
    """마커 time을 로드된 캔들 time과 일치시켜 TV/AIDI 차트에 표시 가능하게 함."""
    times = sorted({int(c["time"]) for c in candles if c.get("time")})
    if not times:
        return markers
    time_set = set(times)
    out: list[dict] = []
    for m in markers:
        raw = int(m.get("time") or 0)
        if raw <= 0:
            continue
        snapped = snap_trade_time_to_candles(raw, times)
        if snapped not in time_set:
            continue
        item = dict(m)
        item["time"] = snapped
        out.append(item)
    return out

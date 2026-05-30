from __future__ import annotations

from dataclasses import dataclass

from .upbit import Candle


def sma(values: list[float], period: int) -> list[float | None]:
    _validate_period(period)
    result: list[float | None] = []
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        result.append(running / period if index >= period - 1 else None)
    return result


def ema(values: list[float], period: int) -> list[float | None]:
    _validate_period(period)
    result: list[float | None] = []
    multiplier = 2 / (period + 1)
    current: float | None = None
    for index, value in enumerate(values):
        if index < period - 1:
            result.append(None)
            continue
        if index == period - 1:
            current = sum(values[:period]) / period
        else:
            current = (value - current) * multiplier + current  # type: ignore[operator]
        result.append(current)
    return result


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    _validate_period(period)
    if len(values) < 2:
        return [None] * len(values)

    gains = [0.0]
    losses = [0.0]
    for previous, current in zip(values, values[1:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(abs(min(change, 0.0)))

    result: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return result

    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    result[period] = _rsi_from_averages(avg_gain, avg_loss)

    for index in range(period + 1, len(values)):
        avg_gain = ((avg_gain * (period - 1)) + gains[index]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[index]) / period
        result[index] = _rsi_from_averages(avg_gain, avg_loss)
    return result


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[list[float | None], list[float | None], list[float | None]]:
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    line: list[float | None] = [
        fast_value - slow_value if fast_value is not None and slow_value is not None else None
        for fast_value, slow_value in zip(fast_ema, slow_ema)
    ]
    compact_line = [value for value in line if value is not None]
    compact_signal = ema(compact_line, signal)
    signal_line: list[float | None] = [None] * (len(line) - len(compact_signal)) + compact_signal
    histogram: list[float | None] = [
        macd_value - signal_value if macd_value is not None and signal_value is not None else None
        for macd_value, signal_value in zip(line, signal_line)
    ]
    return line, signal_line, histogram


def bollinger(values: list[float], period: int = 20, deviations: float = 2.0) -> tuple[list[float | None], list[float | None], list[float | None]]:
    middle = sma(values, period)
    upper: list[float | None] = []
    lower: list[float | None] = []
    for index, average in enumerate(middle):
        if average is None:
            upper.append(None)
            lower.append(None)
            continue
        window = values[index - period + 1 : index + 1]
        variance = sum((value - average) ** 2 for value in window) / period
        stddev = variance**0.5
        upper.append(average + deviations * stddev)
        lower.append(average - deviations * stddev)
    return middle, upper, lower


def atr(candles: list[Candle], period: int = 14) -> list[float | None]:
    _validate_period(period)
    true_ranges: list[float] = []
    previous_close: float | None = None
    for candle in candles:
        high_low = candle.high_price - candle.low_price
        if previous_close is None:
            true_range = high_low
        else:
            true_range = max(high_low, abs(candle.high_price - previous_close), abs(candle.low_price - previous_close))
        true_ranges.append(true_range)
        previous_close = candle.trade_price
    return sma(true_ranges, period)


def volume_average(candles: list[Candle], period: int = 20) -> list[float | None]:
    return sma([candle.candle_acc_trade_volume for candle in candles], period)


def vwap(candles: list[Candle], period: int = 20) -> list[float | None]:
    result: list[float | None] = []
    for index in range(len(candles)):
        if index < period - 1:
            result.append(None)
            continue
        window = candles[index - period + 1 : index + 1]
        volume = sum(candle.candle_acc_trade_volume for candle in window)
        if volume == 0:
            result.append(None)
            continue
        weighted = sum(_typical_price(candle) * candle.candle_acc_trade_volume for candle in window)
        result.append(weighted / volume)
    return result


@dataclass(frozen=True)
class IndicatorSnapshot:
    close: float
    rsi14: float | None
    ema5: float | None
    ema20: float | None
    ema60: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    bb_middle: float | None
    bb_upper: float | None
    bb_lower: float | None
    atr14: float | None
    vwap20: float | None
    volume_ratio20: float | None


def snapshot(candles: list[Candle]) -> IndicatorSnapshot:
    closes = [candle.trade_price for candle in candles]
    rsi_values = rsi(closes)
    ema5 = ema(closes, 5)
    ema20 = ema(closes, 20)
    ema60 = ema(closes, 60)
    macd_line, signal_line, histogram = macd(closes)
    bb_middle, bb_upper, bb_lower = bollinger(closes)
    atr_values = atr(candles)
    vwap_values = vwap(candles)
    volume_avg = volume_average(candles)
    last = candles[-1]
    last_avg_volume = volume_avg[-1]
    volume_ratio = None
    if last_avg_volume and last_avg_volume > 0:
        volume_ratio = last.candle_acc_trade_volume / last_avg_volume
    return IndicatorSnapshot(
        close=last.trade_price,
        rsi14=rsi_values[-1],
        ema5=ema5[-1],
        ema20=ema20[-1],
        ema60=ema60[-1],
        macd=macd_line[-1],
        macd_signal=signal_line[-1],
        macd_histogram=histogram[-1],
        bb_middle=bb_middle[-1],
        bb_upper=bb_upper[-1],
        bb_lower=bb_lower[-1],
        atr14=atr_values[-1],
        vwap20=vwap_values[-1],
        volume_ratio20=volume_ratio,
    )


def percent_change(start: float, end: float) -> float:
    if start == 0:
        return 0.0
    return ((end - start) / start) * 100


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    relative_strength = avg_gain / avg_loss
    return 100 - (100 / (1 + relative_strength))


def _typical_price(candle: Candle) -> float:
    return (candle.high_price + candle.low_price + candle.trade_price) / 3


def _validate_period(period: int) -> None:
    if period <= 0:
        raise ValueError("period must be positive")

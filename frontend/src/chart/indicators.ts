import type { Candle } from "../types";

export type LinePoint = { time: number; value: number };

export type IndicatorBundle = {
  ema20: LinePoint[];
  ema50: LinePoint[];
  ema200: LinePoint[];
  bbUpper: LinePoint[];
  bbMid: LinePoint[];
  bbLower: LinePoint[];
  tenkan: LinePoint[];
  kijun: LinePoint[];
  spanA: LinePoint[];
  spanB: LinePoint[];
  rsi: LinePoint[];
  lastRsi: number | null;
};

function emaArray(closes: number[], period: number): (number | null)[] {
  const n = closes.length;
  const out: (number | null)[] = new Array(n).fill(null);
  if (n < period) return out;
  const alpha = 2 / (period + 1);
  let prev = closes[0];
  out[period - 1] = prev;
  for (let i = 1; i < n; i++) {
    prev = alpha * closes[i] + (1 - alpha) * prev;
    if (i >= period - 1) out[i] = prev;
  }
  return out;
}

function rsiArray(closes: number[], period = 14): (number | null)[] {
  const n = closes.length;
  const out: (number | null)[] = new Array(n).fill(null);
  if (n < period + 1) return out;

  let avgGain = 0;
  let avgLoss = 0;
  for (let i = 1; i <= period; i++) {
    const d = closes[i] - closes[i - 1];
    if (d > 0) avgGain += d;
    else avgLoss -= d;
  }
  avgGain /= period;
  avgLoss /= period;

  const rsiAt = (g: number, l: number) => {
    const loss = l || 1e-9;
    return 100 - 100 / (1 + g / loss);
  };
  out[period] = rsiAt(avgGain, avgLoss);

  for (let i = period + 1; i < n; i++) {
    const d = closes[i] - closes[i - 1];
    const gain = d > 0 ? d : 0;
    const loss = d < 0 ? -d : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    out[i] = rsiAt(avgGain, avgLoss);
  }
  return out;
}

function midHL(highs: number[], lows: number[], end: number, period: number): number {
  const start = Math.max(0, end - period + 1);
  let hi = -Infinity;
  let lo = Infinity;
  for (let i = start; i <= end; i++) {
    if (highs[i] > hi) hi = highs[i];
    if (lows[i] < lo) lo = lows[i];
  }
  return (hi + lo) / 2;
}

function shiftForward(
  times: number[],
  values: (number | null)[],
  shift: number
): LinePoint[] {
  const out: LinePoint[] = [];
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v == null || !Number.isFinite(v)) continue;
    const j = i + shift;
    if (j < times.length) out.push({ time: times[j], value: v });
  }
  return out;
}

function toLinePoints(times: number[], values: (number | null)[]): LinePoint[] {
  const out: LinePoint[] = [];
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v != null && Number.isFinite(v)) out.push({ time: times[i], value: v });
  }
  return out;
}

/** 일목·이평·볼린저·RSI — direction_analyzer / entry_analyzer 와 동일 파라미터 */
export function computeIndicators(candles: Candle[]): IndicatorBundle {
  const empty: IndicatorBundle = {
    ema20: [],
    ema50: [],
    ema200: [],
    bbUpper: [],
    bbMid: [],
    bbLower: [],
    tenkan: [],
    kijun: [],
    spanA: [],
    spanB: [],
    rsi: [],
    lastRsi: null,
  };
  if (candles.length < 30) return empty;

  const times = candles.map((c) => c.time);
  const closes = candles.map((c) => c.close);
  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const n = closes.length;

  const ema20v = emaArray(closes, 20);
  const ema50v = emaArray(closes, 50);
  const ema200p = Math.min(200, n);
  const ema200v = emaArray(closes, ema200p);

  const bbPeriod = 20;
  const bbMult = 2;
  const bbUpper: (number | null)[] = new Array(n).fill(null);
  const bbMid: (number | null)[] = new Array(n).fill(null);
  const bbLower: (number | null)[] = new Array(n).fill(null);
  for (let i = bbPeriod - 1; i < n; i++) {
    const slice = closes.slice(i - bbPeriod + 1, i + 1);
    const mid = slice.reduce((a, b) => a + b, 0) / bbPeriod;
    const variance =
      slice.reduce((s, x) => s + (x - mid) ** 2, 0) / bbPeriod;
    const std = Math.sqrt(variance) || 1e-9;
    bbMid[i] = mid;
    bbUpper[i] = mid + bbMult * std;
    bbLower[i] = mid - bbMult * std;
  }

  const tenkanRaw: (number | null)[] = new Array(n).fill(null);
  const kijunRaw: (number | null)[] = new Array(n).fill(null);
  const spanARaw: (number | null)[] = new Array(n).fill(null);
  const spanBRaw: (number | null)[] = new Array(n).fill(null);

  for (let i = 0; i < n; i++) {
    if (i >= 8) tenkanRaw[i] = midHL(highs, lows, i, 9);
    if (i >= 25) kijunRaw[i] = midHL(highs, lows, i, 26);
    if (tenkanRaw[i] != null && kijunRaw[i] != null) {
      spanARaw[i] = (tenkanRaw[i]! + kijunRaw[i]!) / 2;
    }
    if (i >= 51) spanBRaw[i] = midHL(highs, lows, i, 52);
  }

  const ICHI_SHIFT = 26;
  const spanA = shiftForward(times, spanARaw, ICHI_SHIFT);
  const spanB = shiftForward(times, spanBRaw, ICHI_SHIFT);

  const rsiVals = rsiArray(closes, 14);
  const rsi = toLinePoints(times, rsiVals);
  const lastRsi = rsi.length ? rsi[rsi.length - 1].value : null;

  return {
    ema20: toLinePoints(times, ema20v),
    ema50: toLinePoints(times, ema50v),
    ema200: toLinePoints(times, ema200v),
    bbUpper: toLinePoints(times, bbUpper),
    bbMid: toLinePoints(times, bbMid),
    bbLower: toLinePoints(times, bbLower),
    tenkan: toLinePoints(times, tenkanRaw),
    kijun: toLinePoints(times, kijunRaw),
    spanA,
    spanB,
    rsi,
    lastRsi,
  };
}

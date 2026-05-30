import { useEffect, useRef, useState } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  ColorType,
} from "lightweight-charts";
import type { Candle } from "../types";

type Props = {
  symbol: string;
  pairLabel: string;
  chartInterval: string;
  candles: Candle[];
  chartLoading: boolean;
  chartError: string | null;
  onIntervalChange: (v: string) => void;
};

/** 각 캔들이 의미하는 시간 (1시간봉 = 60분봉, 같은 것) */
const INTERVALS = [
  { v: "1s", label: "1초봉" },
  { v: "1m", label: "1분봉" },
  { v: "15m", label: "15분봉" },
  { v: "1h", label: "1시간" },
  { v: "4h", label: "4시간봉" },
  { v: "1d", label: "일봉" },
];

/** 화면 줌 — 캔들 개수만 조절 (분/시간봉과 무관) */
const ZOOM_OPTIONS = [
  { bars: 50, label: "좁게" },
  { bars: 100, label: "보통" },
  { bars: 150, label: "넓게" },
] as const;

const DEFAULT_VISIBLE_BARS = 100;

export default function ChartPanel({
  symbol,
  pairLabel,
  chartInterval,
  candles,
  chartLoading,
  chartError,
  onIntervalChange,
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const [visibleBars, setVisibleBarsState] = useState(DEFAULT_VISIBLE_BARS);
  const candleCountRef = useRef(0);
  const lastBarTimeRef = useRef<number | null>(null);

  const applyVisibleRange = (barCount: number, visibleBars: number) => {
    const chart = chartRef.current;
    if (!chart || barCount <= 0) return;
    const n = Math.min(visibleBars, barCount);
    if (barCount <= n) {
      chart.timeScale().fitContent();
      return;
    }
    chart.timeScale().setVisibleLogicalRange({
      from: barCount - n,
      to: barCount - 1,
    });
  };

  // symbol 바뀔 때 차트 전체 재생성
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;

    const chart = createChart(el, {
      width: el.clientWidth || 600,
      height: el.clientHeight || 400,
      layout: {
        background: { type: ColorType.Solid, color: "#121820" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "rgba(148,163,184,0.08)" },
        horzLines: { color: "rgba(148,163,184,0.08)" },
      },
      rightPriceScale: {
        borderVisible: false,
        autoScale: true,
        scaleMargins: { top: 0.08, bottom: 0.08 },
      },
      timeScale: {
        borderVisible: false,
        timeVisible: true,
        secondsVisible: chartInterval === "1s",
        rightOffset: chartInterval === "1s" ? 2 : 6,
        barSpacing: chartInterval === "1s" ? 4 : 8,
        minBarSpacing: chartInterval === "1s" ? 2 : 4,
        fixLeftEdge: true,
        lockVisibleTimeRangeOnResize: true,
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
      crosshair: { mode: 1 },
    });

    const candlesSeries = chart.addCandlestickSeries({
      upColor: "#22d3a5",
      downColor: "#f87171",
      borderVisible: false,
      wickUpColor: "#22d3a5",
      wickDownColor: "#f87171",
    });
    const volSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    chart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    chartRef.current = chart;
    candleRef.current = candlesSeries;
    volRef.current = volSeries;

    const ro = new ResizeObserver(() => {
      if (!wrapRef.current) return;
      const w = wrapRef.current.clientWidth;
      const h = wrapRef.current.clientHeight;
      if (w < 10 || h < 10) return;
      chart.applyOptions({ width: w, height: h });
      if (candleCountRef.current > 0) {
        applyVisibleRange(candleCountRef.current, visibleBars);
      }
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volRef.current = null;
    };
  }, [symbol, chartInterval]);

  useEffect(() => {
    if (!candleRef.current || !volRef.current) return;
    if (!candles.length) {
      candleRef.current.setData([]);
      volRef.current.setData([]);
      return;
    }
    const cs = candles.map((c) => ({
      time: c.time as import("lightweight-charts").UTCTimestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    const vs = candles.map((c) => ({
      time: c.time as import("lightweight-charts").UTCTimestamp,
      value: c.volume,
      color:
        c.close >= c.open
          ? "rgba(34,211,165,0.45)"
          : "rgba(248,113,113,0.45)",
    }));

    const prevLen = candleCountRef.current;
    const prevLast = lastBarTimeRef.current;
    const last = cs[cs.length - 1];
    const canPatch =
      prevLen > 0 &&
      last &&
      (cs.length === prevLen || cs.length === prevLen + 1) &&
      prevLast !== null &&
      last.time >= prevLast;

    if (canPatch && candleRef.current && volRef.current) {
      candleRef.current.update(last);
      volRef.current.update(vs[vs.length - 1]);
      if (cs.length > prevLen) {
        candleCountRef.current = cs.length;
        applyVisibleRange(cs.length, visibleBars);
      }
      lastBarTimeRef.current = last.time as number;
      return;
    }

    candleRef.current.setData(cs);
    volRef.current.setData(vs);
    candleCountRef.current = cs.length;
    lastBarTimeRef.current = last ? (last.time as number) : null;
    applyVisibleRange(cs.length, visibleBars);
  }, [candles, visibleBars]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const isSec = chartInterval === "1s";
    const isMin = chartInterval === "1m";
    chart.timeScale().applyOptions({
      secondsVisible: isSec,
      timeVisible: true,
      barSpacing: isSec ? 4 : isMin ? 5 : 8,
      minBarSpacing: isSec ? 2 : 3,
    });
    if (candleCountRef.current > 0) {
      applyVisibleRange(candleCountRef.current, visibleBars);
    }
  }, [chartInterval, visibleBars]);

  const setVisibleBars = (bars: number) => {
    setVisibleBarsState(bars);
  };

  return (
    <div className="chart-panel">
      <div className="chart-toolbar">
        <span className="chart-pair-badge">{pairLabel}</span>
        <div className="chart-tools-wrap">
          <div className="chart-tools">
            <span className="chart-tools-label">봉</span>
            {INTERVALS.map((i) => (
              <button
                key={i.v}
                type="button"
                className={`tool-btn ${chartInterval === i.v ? "active" : ""}`}
                onClick={() => onIntervalChange(i.v)}
                title={
                  i.v === "1h"
                    ? "1시간봉 = 60분봉 (같은 개념)"
                    : `캔들 1개 = ${i.label}`
                }
              >
                {i.label}
              </button>
            ))}
          </div>
          <label className="chart-zoom-select">
            <span className="chart-tools-label">줌</span>
            <select
              value={visibleBars}
              onChange={(e) => setVisibleBars(Number(e.target.value))}
              title="화면에 보이는 캔들 개수 (마우스 휠로도 조절 가능)"
            >
              {ZOOM_OPTIONS.map((r) => (
                <option key={r.bars} value={r.bars}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <div className="chart-canvas-wrap">
        {chartLoading && (
          <div className="chart-overlay">차트 불러오는 중...</div>
        )}
        {!chartLoading && chartError && (
          <div className="chart-overlay error">{chartError}</div>
        )}
        {!chartLoading && !chartError && candles.length === 0 && (
          <div className="chart-overlay">차트 데이터 없음</div>
        )}
        <div className="chart-canvas" ref={wrapRef} />
      </div>
    </div>
  );
}

import { useEffect, useRef } from "react";
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

const INTERVALS = [
  { v: "15m", label: "15분" },
  { v: "1h", label: "1시간" },
  { v: "4h", label: "4시간" },
  { v: "1d", label: "1일" },
];

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
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, timeVisible: true },
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
      chart.applyOptions({
        width: wrapRef.current.clientWidth,
        height: wrapRef.current.clientHeight,
      });
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
    candleRef.current.setData(cs);
    volRef.current.setData(vs);
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  return (
    <div className="chart-panel">
      <div className="chart-toolbar">
        <span className="chart-pair-badge">{pairLabel}</span>
        <div className="chart-tools">
          {INTERVALS.map((i) => (
            <button
              key={i.v}
              type="button"
              className={`tool-btn ${chartInterval === i.v ? "active" : ""}`}
              onClick={() => onIntervalChange(i.v)}
            >
              {i.label}
            </button>
          ))}
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

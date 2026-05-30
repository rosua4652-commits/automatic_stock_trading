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
  interval: string;
  candles: Candle[];
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
  interval,
  candles,
  onIntervalChange,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "rgba(148,163,184,0.08)" },
        horzLines: { color: "rgba(148,163,184,0.08)" },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, timeVisible: true },
      crosshair: { mode: 1 },
      autoSize: true,
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
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    chartRef.current = chart;
    candleRef.current = candlesSeries;
    volRef.current = volSeries;

    const ro = new ResizeObserver(() => {
      if (containerRef.current)
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!candleRef.current || !volRef.current || !candles.length) return;
    const cs = candles.map((c) => ({
      time: c.time as unknown as import("lightweight-charts").Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    const vs = candles.map((c) => ({
      time: c.time as unknown as import("lightweight-charts").Time,
      value: c.volume,
      color:
        c.close >= c.open
          ? "rgba(34,211,165,0.45)"
          : "rgba(248,113,113,0.45)",
    }));
    candleRef.current.setData(cs);
    volRef.current.setData(vs);
    chartRef.current?.timeScale().fitContent();
  }, [candles, symbol]);

  const base = symbol.replace("USDT", "");

  return (
    <div className="chart-panel">
      <div className="chart-toolbar">
        <div className="chart-symbol">
          <span className="symbol-badge">{base}</span>
          <span className="symbol-pair">/ USDT</span>
        </div>
        <div className="chart-tools">
          {INTERVALS.map((i) => (
            <button
              key={i.v}
              type="button"
              className={`tool-btn ${interval === i.v ? "active" : ""}`}
              onClick={() => onIntervalChange(i.v)}
            >
              {i.label}
            </button>
          ))}
        </div>
      </div>
      <div className="chart-canvas" ref={containerRef} />
    </div>
  );
}

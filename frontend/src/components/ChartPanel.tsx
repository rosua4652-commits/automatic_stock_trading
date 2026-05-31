import { useEffect, useMemo, useRef, useState } from "react";
import {
  createChart,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type LineData,
  type SeriesMarker,
  type UTCTimestamp,
  ColorType,
  LineStyle,
} from "lightweight-charts";
import { computeIndicators } from "../chart/indicators";
import type { Candle, ChartMarkerDto, ChartTradeLevels } from "../types";

type Props = {
  symbol: string;
  pairLabel: string;
  chartInterval: string;
  candles: Candle[];
  chartLoading: boolean;
  chartError: string | null;
  tradeLevels?: ChartTradeLevels | null;
  tradeMarkers?: ChartMarkerDto[];
  onIntervalChange: (v: string) => void;
};

const INTERVALS = [
  { v: "1s", label: "1초봉" },
  { v: "1m", label: "1분봉" },
  { v: "15m", label: "15분봉" },
  { v: "1h", label: "1시간" },
  { v: "4h", label: "4시간봉" },
  { v: "1d", label: "일봉" },
];

const ZOOM_OPTIONS = [
  { bars: 50, label: "좁게" },
  { bars: 100, label: "보통" },
  { bars: 150, label: "넓게" },
] as const;

const DEFAULT_VISIBLE_BARS = 100;
const MIN_MAIN_W = 80;
const MIN_MAIN_H = 120;
const MIN_RSI_H = 48;

type OverlayToggles = {
  ichimoku: boolean;
  ema: boolean;
  bb: boolean;
  rsi: boolean;
};

const LEGEND = [
  { key: "ichimoku" as const, label: "일목", items: ["전환·기준·선행스팬 A/B (26봉 선행)"] },
  { key: "ema" as const, label: "이평", items: ["EMA20", "EMA50", "EMA200"] },
  { key: "bb" as const, label: "BB", items: ["상·중·하단"] },
  { key: "rsi" as const, label: "RSI", items: ["14"] },
];

function toUtc(data: LineData[]): LineData<UTCTimestamp>[] {
  return data.map((d) => ({
    time: d.time as UTCTimestamp,
    value: d.value,
  }));
}

export default function ChartPanel({
  symbol,
  pairLabel,
  chartInterval,
  candles,
  chartLoading,
  chartError,
  tradeLevels,
  tradeMarkers = [],
  onIntervalChange,
}: Props) {
  const mainWrapRef = useRef<HTMLDivElement>(null);
  const rsiWrapRef = useRef<HTMLDivElement>(null);
  const mainChartRef = useRef<IChartApi | null>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const overlayRefs = useRef<Record<string, ISeriesApi<"Line"> | null>>({});
  const rsiLineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rsi30Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const rsi70Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const priceLineRefs = useRef<IPriceLine[]>([]);

  const [visibleBars, setVisibleBarsState] = useState(DEFAULT_VISIBLE_BARS);
  const [overlays, setOverlays] = useState<OverlayToggles>({
    ichimoku: true,
    ema: true,
    bb: true,
    rsi: true,
  });
  const candleCountRef = useRef(0);
  const lastBarTimeRef = useRef<number | null>(null);
  const syncingRef = useRef(false);
  const visibleBarsRef = useRef(visibleBars);
  visibleBarsRef.current = visibleBars;

  const indicators = useMemo(() => computeIndicators(candles), [candles]);

  const applyVisibleRange = (barCount: number, bars: number) => {
    const chart = mainChartRef.current;
    if (!chart || barCount <= 0) return;
    const n = Math.min(bars, barCount);
    const range =
      barCount <= n
        ? null
        : { from: barCount - n, to: barCount - 1 };
    syncingRef.current = true;
    if (range) {
      chart.timeScale().setVisibleLogicalRange(range);
      rsiChartRef.current?.timeScale().setVisibleLogicalRange(range);
    } else {
      chart.timeScale().fitContent();
      rsiChartRef.current?.timeScale().fitContent();
    }
    syncingRef.current = false;
  };

  const setSeriesVisible = (key: string, visible: boolean) => {
    const s = overlayRefs.current[key];
    if (s) s.applyOptions({ visible });
  };

  const applyOverlayVisibility = (t: OverlayToggles) => {
    const ichKeys = ["tenkan", "kijun", "spanA", "spanB"];
    ichKeys.forEach((k) => setSeriesVisible(k, t.ichimoku));
    ["ema20", "ema50", "ema200"].forEach((k) => setSeriesVisible(k, t.ema));
    ["bbUpper", "bbMid", "bbLower"].forEach((k) => setSeriesVisible(k, t.bb));
    rsiLineRef.current?.applyOptions({ visible: t.rsi });
    rsi30Ref.current?.applyOptions({ visible: t.rsi });
    rsi70Ref.current?.applyOptions({ visible: t.rsi });
    if (rsiWrapRef.current) {
      rsiWrapRef.current.style.display = t.rsi ? "" : "none";
    }
  };

  const resizeCharts = () => {
    const mainEl = mainWrapRef.current;
    const rsiEl = rsiWrapRef.current;
    const mainChart = mainChartRef.current;
    const rsiChart = rsiChartRef.current;
    if (!mainEl || !rsiEl || !mainChart || !rsiChart) return;
    const mw = mainEl.clientWidth;
    const mh = mainEl.clientHeight;
    const rw = rsiEl.clientWidth;
    const rh = rsiEl.clientHeight;
    if (mw < MIN_MAIN_W || mh < MIN_MAIN_H) return;
    mainChart.applyOptions({ width: mw, height: mh });
    rsiChart.applyOptions({ width: rw, height: Math.max(rh, MIN_RSI_H) });
    if (candleCountRef.current > 0) {
      applyVisibleRange(candleCountRef.current, visibleBarsRef.current);
    }
  };

  useEffect(() => {
    const mainEl = mainWrapRef.current;
    const rsiEl = rsiWrapRef.current;
    if (!mainEl || !rsiEl) return;

    let disposed = false;

    const chartOpts = {
      layout: {
        background: { type: ColorType.Solid, color: "#121820" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "rgba(148,163,184,0.08)" },
        horzLines: { color: "rgba(148,163,184,0.08)" },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: {
        borderVisible: false,
        timeVisible: true,
        secondsVisible: chartInterval === "1s",
        rightOffset: chartInterval === "1s" ? 2 : 6,
        barSpacing: chartInterval === "1s" ? 4 : 8,
        minBarSpacing: chartInterval === "1s" ? 2 : 4,
        fixLeftEdge: true,
      },
      crosshair: { mode: 1 as const },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
    };

    const measure = () => ({
      mw: mainEl.clientWidth,
      mh: mainEl.clientHeight,
      rw: rsiEl.clientWidth,
      rh: rsiEl.clientHeight,
    });

    const canInit = () => {
      const { mw, mh, rw, rh } = measure();
      return mw >= MIN_MAIN_W && mh >= MIN_MAIN_H && rw >= MIN_MAIN_W && rh >= MIN_RSI_H;
    };

    let mainChart: IChartApi | null = null;
    let rsiChart: IChartApi | null = null;
    let bootRo: ResizeObserver | null = null;
    let roMain: ResizeObserver | null = null;
    let roRsi: ResizeObserver | null = null;

    const buildCharts = () => {
      if (disposed || mainChartRef.current || !canInit()) return false;
      const { mw, mh, rw, rh } = measure();

      mainChart = createChart(mainEl, {
      ...chartOpts,
      width: mw,
      height: mh,
      rightPriceScale: {
        borderVisible: false,
        autoScale: true,
        scaleMargins: { top: 0.06, bottom: 0.12 },
      },
    });

      rsiChart = createChart(rsiEl, {
      ...chartOpts,
      width: rw,
      height: rh,
      rightPriceScale: {
        borderVisible: false,
        autoScale: false,
        scaleMargins: { top: 0.1, bottom: 0.05 },
      },
      timeScale: { ...chartOpts.timeScale, visible: false },
    });

    const candleSeries = mainChart.addCandlestickSeries({
      upColor: "#22d3a5",
      downColor: "#f87171",
      borderVisible: false,
      wickUpColor: "#22d3a5",
      wickDownColor: "#f87171",
    });
    const volSeries = mainChart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    mainChart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    const line = (
      key: string,
      color: string,
      width = 1,
      style?: number
    ) => {
      const s = mainChart.addLineSeries({
        color,
        lineWidth: width,
        lineStyle: style,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      overlayRefs.current[key] = s;
      return s;
    };

    line("ema20", "#fbbf24", 1);
    line("ema50", "#38bdf8", 1);
    line("ema200", "#c084fc", 1);
    line("bbUpper", "rgba(167,139,250,0.85)", 1, LineStyle.Dashed);
    line("bbMid", "rgba(167,139,250,0.55)", 1);
    line("bbLower", "rgba(167,139,250,0.85)", 1, LineStyle.Dashed);
    line("tenkan", "#fb923c", 1);
    line("kijun", "#60a5fa", 1);
    line("spanA", "rgba(74,222,128,0.8)", 1, LineStyle.Dashed);
    line("spanB", "rgba(248,113,113,0.8)", 1, LineStyle.Dashed);

    const rsiLine = rsiChart.addLineSeries({
      color: "#a78bfa",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    const rsi30 = rsiChart.addLineSeries({
      color: "rgba(148,163,184,0.35)",
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    const rsi70 = rsiChart.addLineSeries({
      color: "rgba(148,163,184,0.35)",
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    rsiChart.priceScale("right").applyOptions({
      autoScale: true,
    });

      mainChartRef.current = mainChart;
      rsiChartRef.current = rsiChart;
      candleRef.current = candleSeries;
      volRef.current = volSeries;
      rsiLineRef.current = rsiLine;
      rsi30Ref.current = rsi30;
      rsi70Ref.current = rsi70;

        const syncFromMain = () => {
        if (syncingRef.current || !mainChart || !rsiChart) return;
        const range = mainChart.timeScale().getVisibleLogicalRange();
        if (!range) return;
        syncingRef.current = true;
        rsiChart.timeScale().setVisibleLogicalRange(range);
        syncingRef.current = false;
      };
      const syncFromRsi = () => {
        if (syncingRef.current || !mainChart || !rsiChart) return;
        const range = rsiChart.timeScale().getVisibleLogicalRange();
        if (!range) return;
        syncingRef.current = true;
        mainChart.timeScale().setVisibleLogicalRange(range);
        syncingRef.current = false;
      };
      mainChart.timeScale().subscribeVisibleLogicalRangeChange(syncFromMain);
      rsiChart.timeScale().subscribeVisibleLogicalRangeChange(syncFromRsi);

      roMain = new ResizeObserver(() => resizeCharts());
      roRsi = new ResizeObserver(() => resizeCharts());
      roMain.observe(mainEl);
      roRsi.observe(rsiEl);

      applyOverlayVisibility(overlays);
      requestAnimationFrame(() => resizeCharts());
      return true;
    };

    if (!buildCharts()) {
      bootRo = new ResizeObserver(() => {
        if (buildCharts()) bootRo?.disconnect();
      });
      bootRo.observe(mainEl);
      bootRo.observe(rsiEl);
    }

    return () => {
      disposed = true;
      bootRo?.disconnect();
      roMain?.disconnect();
      roRsi?.disconnect();
      if (mainChart) {
        mainChart.remove();
      }
      if (rsiChart) {
        rsiChart.remove();
      }
      mainChartRef.current = null;
      rsiChartRef.current = null;
      candleRef.current = null;
      volRef.current = null;
      rsiLineRef.current = null;
      rsi30Ref.current = null;
      rsi70Ref.current = null;
      overlayRefs.current = {};
    };
  }, [symbol, chartInterval]);

  useEffect(() => {
    applyOverlayVisibility(overlays);
  }, [overlays]);

  useEffect(() => {
    if (!candleRef.current || !volRef.current) return;
    if (!candles.length) {
      candleRef.current.setData([]);
      volRef.current.setData([]);
      Object.values(overlayRefs.current).forEach((s) => s?.setData([]));
      rsiLineRef.current?.setData([]);
      rsi30Ref.current?.setData([]);
      rsi70Ref.current?.setData([]);
      return;
    }

    const cs = candles.map((c) => ({
      time: c.time as UTCTimestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    const vs = candles.map((c) => ({
      time: c.time as UTCTimestamp,
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
    } else {
      candleRef.current.setData(cs);
      volRef.current.setData(vs);
      candleCountRef.current = cs.length;
      lastBarTimeRef.current = last ? (last.time as number) : null;
      applyVisibleRange(cs.length, visibleBars);
    }

    // 지표는 매 틱마다 갱신 (실시간 봉 반영)

    const setLine = (key: string, points: { time: number; value: number }[]) => {
      const s = overlayRefs.current[key] as ISeriesApi<"Line"> | undefined;
      if (s && "setData" in s) s.setData(toUtc(points as LineData[]));
    };
    setLine("ema20", indicators.ema20);
    setLine("ema50", indicators.ema50);
    setLine("ema200", indicators.ema200);
    setLine("bbUpper", indicators.bbUpper);
    setLine("bbMid", indicators.bbMid);
    setLine("bbLower", indicators.bbLower);
    setLine("tenkan", indicators.tenkan);
    setLine("kijun", indicators.kijun);
    setLine("spanA", indicators.spanA);
    setLine("spanB", indicators.spanB);

    const rsiData = toUtc(indicators.rsi as LineData[]);
    rsiLineRef.current?.setData(rsiData);
    if (rsiData.length > 0) {
      const t0 = rsiData[0].time;
      const t1 = rsiData[rsiData.length - 1].time;
      rsi30Ref.current?.setData([
        { time: t0, value: 30 },
        { time: t1, value: 30 },
      ]);
      rsi70Ref.current?.setData([
        { time: t0, value: 70 },
        { time: t1, value: 70 },
      ]);
    }
    requestAnimationFrame(() => resizeCharts());
  }, [candles, indicators, visibleBars]);

  useEffect(() => {
    const series = candleRef.current;
    if (!series) return;
    priceLineRefs.current.forEach((line) => {
      try {
        series.removePriceLine(line);
      } catch {
        /* ignore */
      }
    });
    priceLineRefs.current = [];

    const lv = tradeLevels;
    if (!lv || lv.kind === "none") {
      return;
    }
    const dashed = lv.kind === "proposal" || lv.kind === "estimate";
    const addLine = (
      price: number | null | undefined,
      color: string,
      title: string
    ) => {
      if (price == null || price <= 0) return;
      const line = series.createPriceLine({
        price,
        color,
        lineWidth: 2,
        lineStyle: dashed ? LineStyle.Dashed : LineStyle.Solid,
        axisLabelVisible: true,
        title,
      });
      priceLineRefs.current.push(line);
    };
    const entryTitle =
      lv.kind === "position"
        ? "진입(평단)"
        : lv.kind === "proposal"
          ? "진입(제안)"
          : "현재가";
    addLine(lv.entry, "#38bdf8", entryTitle);
    addLine(
      lv.stop_loss,
      "#f87171",
      `손절${lv.stop_loss_pct ? ` ${lv.stop_loss_pct}%` : ""}`
    );
    addLine(
      lv.take_profit,
      "#22d3a5",
      `익절${lv.take_profit_pct ? ` ${lv.take_profit_pct}%` : ""}`
    );
  }, [tradeLevels, candles.length, symbol]);

  useEffect(() => {
    const series = candleRef.current;
    if (!series) return;
    const markers: SeriesMarker<UTCTimestamp>[] = tradeMarkers
      .filter((m) => m.time > 0 && m.price > 0)
      .map((m) => ({
        time: m.time as UTCTimestamp,
        position: m.side === "BUY" ? ("belowBar" as const) : ("aboveBar" as const),
        color: m.side === "BUY" ? "#22d3a5" : "#f87171",
        shape: m.side === "BUY" ? ("arrowUp" as const) : ("arrowDown" as const),
        text: m.text?.slice(0, 12) || m.side,
      }));
    series.setMarkers(markers);
  }, [tradeMarkers, candles.length, symbol]);

  useEffect(() => {
    const main = mainChartRef.current;
    const rsi = rsiChartRef.current;
    if (!main) return;
    const isSec = chartInterval === "1s";
    const isMin = chartInterval === "1m";
    main.timeScale().applyOptions({
      secondsVisible: isSec,
      timeVisible: true,
      barSpacing: isSec ? 4 : isMin ? 5 : 8,
      minBarSpacing: isSec ? 2 : 3,
    });
    rsi?.timeScale().applyOptions({
      secondsVisible: isSec,
      barSpacing: isSec ? 4 : isMin ? 5 : 8,
      minBarSpacing: isSec ? 2 : 3,
    });
    if (candleCountRef.current > 0) {
      applyVisibleRange(candleCountRef.current, visibleBars);
    }
  }, [chartInterval, visibleBars]);

  const toggleOverlay = (key: keyof OverlayToggles) => {
    setOverlays((o) => ({ ...o, [key]: !o[key] }));
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
              onChange={(e) => setVisibleBarsState(Number(e.target.value))}
              title="화면에 보이는 캔들 개수"
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

      <div className="chart-indicator-bar">
        <span className="chart-tools-label">지표</span>
        {LEGEND.map((g) => (
          <button
            key={g.key}
            type="button"
            className={`indicator-toggle ${overlays[g.key] ? "on" : ""}`}
            onClick={() => toggleOverlay(g.key)}
            title={g.items.join(" · ")}
          >
            {g.label}
            {g.key === "rsi" && indicators.lastRsi != null && overlays.rsi && (
              <span className="indicator-rsi-val">
                {indicators.lastRsi.toFixed(0)}
              </span>
            )}
          </button>
        ))}
        <div className="chart-legend-colors" aria-hidden>
          <span style={{ color: "#fb923c" }}>전환</span>
          <span style={{ color: "#60a5fa" }}>기준</span>
          <span style={{ color: "#fbbf24" }}>E20</span>
          <span style={{ color: "#38bdf8" }}>E50</span>
          <span style={{ color: "#a78bfa" }}>BB·RSI</span>
        </div>
        {tradeLevels && tradeLevels.kind !== "none" && (
          <div className="chart-level-legend" title={tradeLevels.label}>
            <span style={{ color: "#38bdf8" }}>진입</span>
            <span style={{ color: "#f87171" }}>손절</span>
            <span style={{ color: "#22d3a5" }}>익절</span>
            <span className="chart-level-kind">
              {tradeLevels.kind === "position"
                ? "보유"
                : tradeLevels.kind === "proposal"
                  ? "AI제안"
                  : "예상"}
            </span>
          </div>
        )}
      </div>

      <div className="chart-canvas-wrap chart-canvas-stack">
        {chartLoading && (
          <div className="chart-overlay">차트 불러오는 중...</div>
        )}
        {!chartLoading && chartError && (
          <div className="chart-overlay error">{chartError}</div>
        )}
        {!chartLoading && !chartError && candles.length === 0 && (
          <div className="chart-overlay">차트 데이터 없음</div>
        )}
        <div className="chart-canvas chart-canvas-main" ref={mainWrapRef} />
        <div
          className={`chart-canvas chart-canvas-rsi ${overlays.rsi ? "" : "hidden"}`}
          ref={rsiWrapRef}
        />
      </div>
    </div>
  );
}

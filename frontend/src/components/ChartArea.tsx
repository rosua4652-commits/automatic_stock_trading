import { useMemo } from "react";
import { computeIndicators } from "../chart/indicators";
import type { Candle, ChartMarkerDto, ChartTradeLevels } from "../types";
import type { ChartOverlays } from "../utils/chartPrefs";
import type { ChartEngine } from "../utils/chartEngine";
import ChartPanel from "./ChartPanel";
import TradingViewChartPanel from "./TradingViewChartPanel";

type Props = {
  symbol: string;
  pairLabel: string;
  chartInterval: string;
  chartEngine: ChartEngine;
  chartOverlays: ChartOverlays;
  chartVisibleBars: number;
  candles: Candle[];
  chartLoading: boolean;
  chartError: string | null;
  tradeLevels?: ChartTradeLevels | null;
  tradeMarkers?: ChartMarkerDto[];
  onIntervalChange: (v: string) => void;
  onEngineChange: (engine: ChartEngine) => void;
  onOverlayToggle: (key: keyof ChartOverlays) => void;
  onVisibleBarsChange: (bars: number) => void;
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

const LEGEND = [
  { key: "ichimoku" as const, label: "일목", items: ["전환·기준·선행스팬 A/B"] },
  { key: "ema" as const, label: "이평", items: ["EMA20", "EMA50", "EMA200"] },
  { key: "bb" as const, label: "BB", items: ["상·중·하단"] },
  { key: "rsi" as const, label: "RSI", items: ["14"] },
];

export default function ChartArea({
  chartEngine,
  onEngineChange,
  chartOverlays,
  chartVisibleBars,
  onOverlayToggle,
  onVisibleBarsChange,
  chartInterval,
  onIntervalChange,
  candles,
  tradeMarkers,
  tradeLevels,
  pairLabel,
  ...props
}: Props) {
  const indicators = useMemo(() => computeIndicators(candles), [candles]);
  const markerCount = tradeMarkers?.length ?? 0;
  const onAidi = chartEngine === "aidi";

  return (
    <div className={`chart-area chart-area-${chartEngine}`}>
      <div className="chart-engine-bar">
        <span className="chart-tools-label">차트</span>
        <div className="chart-tools">
          <button
            type="button"
            className={`tool-btn ${chartEngine === "aidi" ? "active" : ""}`}
            onClick={() => onEngineChange("aidi")}
            title="매수·매도 마커 · 지표 · 손익절선"
          >
            AIDI
          </button>
          <button
            type="button"
            className={`tool-btn ${chartEngine === "tradingview" ? "active" : ""}`}
            onClick={() => onEngineChange("tradingview")}
            title="업비트 TradingView"
          >
            업비트 TV
          </button>
        </div>
        {onAidi && markerCount > 0 && (
          <span className="chart-engine-note">매매 {markerCount}건 표시</span>
        )}
        {!onAidi && markerCount > 0 && (
          <span className="chart-engine-note chart-engine-note-warn">
            매매 {markerCount}건 — AIDI 탭에서 캔들 표시
          </span>
        )}
      </div>

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
              >
                {i.label}
              </button>
            ))}
          </div>
          <label className="chart-zoom-select">
            <span className="chart-tools-label">줌</span>
            <select
              value={chartVisibleBars}
              onChange={(e) => onVisibleBarsChange(Number(e.target.value))}
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
            className={`indicator-toggle ${chartOverlays[g.key] ? "on" : ""}`}
            onClick={() => onOverlayToggle(g.key)}
            title={
              onAidi
                ? g.items.join(" · ")
                : `${g.items.join(" · ")} — AIDI 차트에서 표시`
            }
          >
            {g.label}
            {g.key === "rsi" &&
              onAidi &&
              indicators.lastRsi != null &&
              chartOverlays.rsi && (
                <span className="indicator-rsi-val">
                  {indicators.lastRsi.toFixed(0)}
                </span>
              )}
          </button>
        ))}
        {!onAidi && (
          <span className="chart-engine-note">AIDI 탭에서 지표 표시</span>
        )}
        {onAidi && tradeLevels && tradeLevels.kind !== "none" && (
          <div className="chart-level-legend" title={tradeLevels.label}>
            <span style={{ color: "#38bdf8" }}>진입</span>
            <span style={{ color: "#f87171" }}>손절</span>
            <span style={{ color: "#22d3a5" }}>익절</span>
          </div>
        )}
      </div>

      {chartEngine === "tradingview" ? (
        <TradingViewChartPanel symbol={props.symbol} chartInterval={chartInterval} />
      ) : (
        <ChartPanel
          {...props}
          pairLabel={pairLabel}
          chartInterval={chartInterval}
          chartOverlays={chartOverlays}
          chartVisibleBars={chartVisibleBars}
          candles={candles}
          tradeLevels={tradeLevels}
          tradeMarkers={tradeMarkers}
        />
      )}
    </div>
  );
}

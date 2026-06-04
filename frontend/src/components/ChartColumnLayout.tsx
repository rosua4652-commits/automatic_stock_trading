import { useCallback, useEffect, useRef, useState } from "react";
import type {
  AppConfig,
  Candle,
  ChartMarkerDto,
  ChartTradeLevels,
  CoinView,
  InvestmentRecommendation,
  TabQuote,
} from "../types";
import type { ChartOverlays, ChartPrefsPatch } from "../utils/chartPrefs";
import type { ChartEngine } from "../utils/chartEngine";
import { fmtKrw, fmtPct } from "../utils";
import ChartArea from "./ChartArea";
import CoinDetailBar from "./CoinDetailBar";

const MIN_H = 240;
const MAX_H = 2000;

function defaultHeight(): number {
  return Math.round(Math.max(MIN_H, window.innerHeight * 0.58));
}

function resolveInitialHeight(saved: number): number {
  if (saved >= MIN_H) return saved;
  return defaultHeight();
}

type Props = {
  view: CoinView;
  botStatus: string;
  botMessage: string;
  canTrade: boolean;
  busy: boolean;
  cashKrw: number;
  config: AppConfig;
  recommendation?: InvestmentRecommendation | null;
  tabQuote?: TabQuote;
  surgeTags?: Record<string, string>;
  onBuy: (symbol: string, amountKrw: number) => Promise<void>;
  onSell: (symbol: string, percent: number) => Promise<void>;
  symbol: string;
  pairLabel: string;
  chartInterval: string;
  chartEngine: ChartEngine;
  chartOverlays: ChartOverlays;
  chartVisibleBars: number;
  tradeCollapsed: boolean;
  initialPaneHeight: number;
  candles: Candle[];
  chartLoading: boolean;
  chartError: string | null;
  tradeLevels?: ChartTradeLevels | null;
  tradeMarkers?: ChartMarkerDto[];
  onIntervalChange: (v: string) => void;
  onEngineChange: (engine: ChartEngine) => void;
  onOverlayToggle: (key: keyof ChartOverlays) => void;
  onVisibleBarsChange: (bars: number) => void;
  onChartPrefsChange: (patch: ChartPrefsPatch) => void;
};

export default function ChartColumnLayout({
  view,
  botStatus,
  botMessage,
  canTrade,
  busy,
  cashKrw,
  config,
  recommendation,
  tabQuote,
  surgeTags,
  onBuy,
  onSell,
  symbol,
  pairLabel,
  chartInterval,
  chartEngine,
  chartOverlays,
  chartVisibleBars,
  tradeCollapsed,
  initialPaneHeight,
  candles,
  chartLoading,
  chartError,
  tradeLevels,
  tradeMarkers,
  onIntervalChange,
  onEngineChange,
  onOverlayToggle,
  onVisibleBarsChange,
  onChartPrefsChange,
}: Props) {
  const columnRef = useRef<HTMLDivElement>(null);
  const [chartHeight, setChartHeight] = useState<number>(() =>
    resolveInitialHeight(initialPaneHeight)
  );
  const dragRef = useRef<{ startY: number; startH: number } | null>(null);
  const prevPaneHeightRef = useRef(initialPaneHeight);

  useEffect(() => {
    if (prevPaneHeightRef.current === initialPaneHeight) return;
    prevPaneHeightRef.current = initialPaneHeight;
    if (initialPaneHeight >= MIN_H) {
      setChartHeight(initialPaneHeight);
    }
  }, [initialPaneHeight]);

  const clampHeight = useCallback((h: number) => {
    return Math.min(MAX_H, Math.max(MIN_H, Math.round(h)));
  }, []);

  useEffect(() => {
    const onResize = () => {
      setChartHeight((h) => clampHeight(h));
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [clampHeight]);

  const persistHeight = useCallback(
    (h: number) => {
      const c = clampHeight(h);
      onChartPrefsChange({ chartPaneHeight: c });
      return c;
    },
    [clampHeight, onChartPrefsChange]
  );

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    dragRef.current = { startY: e.clientY, startH: chartHeight };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return;
    const delta = dragRef.current.startY - e.clientY;
    const next = clampHeight(dragRef.current.startH + delta);
    setChartHeight(next);
  };

  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return;
    dragRef.current = null;
    e.currentTarget.releasePointerCapture(e.pointerId);
    setChartHeight((h) => persistHeight(h));
  };

  const resetHeight = () => {
    const h = defaultHeight();
    setChartHeight(h);
    persistHeight(h);
  };

  const priceKrw =
    tabQuote?.price_krw ??
    (view.price_usdt > 0 ? Math.round(view.price_usdt * 1400) : 0);
  const change24h = tabQuote?.change_24h ?? view.change_24h ?? 0;
  const coinName = view.meta.name_ko || view.meta.base;

  return (
    <div className="chart-column" ref={columnRef}>
      <div className={`chart-trade-pane ${tradeCollapsed ? "collapsed" : ""}`}>
        <div className="chart-trade-pane-header">
          {tradeCollapsed ? (
            <div className="chart-trade-mini">
              <span className="chart-trade-mini-name">{coinName}</span>
              <span className="chart-trade-mini-price">
                {priceKrw > 0 ? `${fmtKrw(priceKrw)}원` : "—"}
              </span>
              <span
                className={`chart-trade-mini-change ${change24h >= 0 ? "up" : "down"}`}
              >
                {fmtPct(change24h)}
              </span>
              <button
                type="button"
                className="chart-trade-collapse-btn"
                onClick={() => onChartPrefsChange({ chartTradeCollapsed: false })}
              >
                매매 펼치기
              </button>
            </div>
          ) : (
            <>
              <div className="chart-trade-pane-toolbar">
                <button
                  type="button"
                  className="chart-trade-collapse-btn"
                  onClick={() => onChartPrefsChange({ chartTradeCollapsed: true })}
                >
                  매매 접기
                </button>
              </div>
              <CoinDetailBar
                view={view}
                botStatus={botStatus}
                botMessage={botMessage}
                canTrade={canTrade}
                busy={busy}
                cashKrw={cashKrw}
                config={config}
                recommendation={recommendation}
                tabQuote={tabQuote}
                surgeTags={surgeTags}
                onBuy={onBuy}
                onSell={onSell}
              />
            </>
          )}
        </div>
      </div>
      {!tradeCollapsed && (
        <div
          className="chart-resize-handle"
          role="separator"
          aria-orientation="horizontal"
          aria-label="차트 높이 조절 — 위로 끌면 차트 확대"
          title="드래그: 차트 높이 · 더블클릭: 기본 크기"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onDoubleClick={resetHeight}
        />
      )}
      <div
        className={`chart-pane-resizable${tradeCollapsed ? " chart-pane-fill" : ""}`}
        style={tradeCollapsed ? undefined : { height: chartHeight }}
      >
        <ChartArea
          symbol={symbol}
          pairLabel={pairLabel}
          chartInterval={chartInterval}
          chartEngine={chartEngine}
          chartOverlays={chartOverlays}
          chartVisibleBars={chartVisibleBars}
          candles={candles}
          chartLoading={chartLoading}
          chartError={chartError}
          tradeLevels={tradeLevels}
          tradeMarkers={tradeMarkers}
          onIntervalChange={onIntervalChange}
          onEngineChange={onEngineChange}
          onOverlayToggle={onOverlayToggle}
          onVisibleBarsChange={onVisibleBarsChange}
        />
      </div>
    </div>
  );
}

import type { AppConfig } from "../types";
import type { ChartEngine } from "./chartEngine";

export type ChartOverlays = {
  ichimoku: boolean;
  ema: boolean;
  bb: boolean;
  rsi: boolean;
};

export type ChartPrefs = {
  chartEngine: ChartEngine;
  chartInterval: string;
  chartPaneHeight: number;
  chartTradeCollapsed: boolean;
  chartVisibleBars: number;
  chartOverlays: ChartOverlays;
};

export type ChartPrefsPatch = Partial<ChartPrefs> & {
  chartOverlays?: Partial<ChartOverlays>;
};

const LS_ENGINE = "aidi-chart-engine";
const LS_PANE_HEIGHT = "aidi-chart-pane-height";
const VALID_INTERVALS = new Set(["1s", "1m", "15m", "1h", "4h", "1d"]);

export function chartPrefsFromConfig(cfg: AppConfig): ChartPrefs {
  const engine: ChartEngine = cfg.chart_engine === "aidi" ? "aidi" : "tradingview";
  const interval = cfg.chart_interval && VALID_INTERVALS.has(cfg.chart_interval)
    ? cfg.chart_interval
    : "1h";
  return {
    chartEngine: engine,
    chartInterval: interval,
    chartPaneHeight: cfg.chart_pane_height ?? 0,
    chartTradeCollapsed: cfg.chart_trade_collapsed ?? false,
    chartVisibleBars: cfg.chart_visible_bars ?? 100,
    chartOverlays: {
      ichimoku: cfg.chart_overlay_ichimoku ?? true,
      ema: cfg.chart_overlay_ema ?? true,
      bb: cfg.chart_overlay_bb ?? true,
      rsi: cfg.chart_overlay_rsi ?? true,
    },
  };
}

export function mergeChartPrefsPatch(
  current: ChartPrefs,
  patch: ChartPrefsPatch
): ChartPrefs {
  const overlays = patch.chartOverlays
    ? { ...current.chartOverlays, ...patch.chartOverlays }
    : current.chartOverlays;
  return {
    chartEngine: patch.chartEngine ?? current.chartEngine,
    chartInterval: patch.chartInterval ?? current.chartInterval,
    chartPaneHeight: patch.chartPaneHeight ?? current.chartPaneHeight,
    chartTradeCollapsed: patch.chartTradeCollapsed ?? current.chartTradeCollapsed,
    chartVisibleBars: patch.chartVisibleBars ?? current.chartVisibleBars,
    chartOverlays: overlays,
  };
}

export function chartPrefsToApiBody(prefs: ChartPrefs): Record<string, unknown> {
  return {
    chart_engine: prefs.chartEngine,
    chart_interval: prefs.chartInterval,
    chart_pane_height: prefs.chartPaneHeight,
    chart_trade_collapsed: prefs.chartTradeCollapsed,
    chart_visible_bars: prefs.chartVisibleBars,
    chart_overlay_ichimoku: prefs.chartOverlays.ichimoku,
    chart_overlay_ema: prefs.chartOverlays.ema,
    chart_overlay_bb: prefs.chartOverlays.bb,
    chart_overlay_rsi: prefs.chartOverlays.rsi,
  };
}

export function chartPrefsToConfigPatch(
  prefs: ChartPrefsPatch,
  existing: AppConfig
): AppConfig {
  const base = chartPrefsFromConfig(existing);
  const overlays = prefs.chartOverlays
    ? { ...base.chartOverlays, ...prefs.chartOverlays }
    : base.chartOverlays;

  return {
    ...existing,
    chart_engine: prefs.chartEngine ?? base.chartEngine,
    chart_interval: prefs.chartInterval ?? base.chartInterval,
    chart_pane_height: prefs.chartPaneHeight ?? base.chartPaneHeight,
    chart_trade_collapsed: prefs.chartTradeCollapsed ?? base.chartTradeCollapsed,
    chart_visible_bars: prefs.chartVisibleBars ?? base.chartVisibleBars,
    chart_overlay_ichimoku: overlays.ichimoku,
    chart_overlay_ema: overlays.ema,
    chart_overlay_bb: overlays.bb,
    chart_overlay_rsi: overlays.rsi,
  };
}

/** localStorage → config (한 번만, 초기 로드 시) */
export function migrateChartPrefsFromLocalStorage(cfg: AppConfig): {
  config: AppConfig;
  didMigrate: boolean;
} {
  let didMigrate = false;
  let next = { ...cfg };

  const lsEngine = localStorage.getItem(LS_ENGINE);
  if (lsEngine === "aidi" || lsEngine === "tradingview") {
    if (next.chart_engine !== lsEngine) {
      next.chart_engine = lsEngine;
      didMigrate = true;
    }
    localStorage.removeItem(LS_ENGINE);
  }

  const lsHeight = localStorage.getItem(LS_PANE_HEIGHT);
  if (lsHeight) {
    const n = Number(lsHeight);
    if (Number.isFinite(n) && n >= 240) {
      const cur = next.chart_pane_height ?? 0;
      if (cur === 0) {
        next.chart_pane_height = Math.round(Math.min(2000, n));
        didMigrate = true;
      }
    }
    localStorage.removeItem(LS_PANE_HEIGHT);
  }

  return { config: next, didMigrate };
}

export type ChartEngine = "aidi" | "tradingview";

const STORAGE_KEY = "aidi-chart-engine";

export function loadChartEngine(): ChartEngine {
  const v = localStorage.getItem(STORAGE_KEY);
  if (v === "aidi") return "aidi";
  return "tradingview";
}

export function saveChartEngine(engine: ChartEngine): void {
  localStorage.setItem(STORAGE_KEY, engine);
}

/** AIDI 심볼 → 업비트 TradingView 심볼 */
export function upbitTvSymbol(symbol: string): string {
  const base = symbol.toUpperCase().replace("USDT", "").replace("USD", "");
  return `UPBIT:${base}KRW`;
}

export function tvInterval(interval: string): string {
  const map: Record<string, string> = {
    "1s": "1",
    "1m": "1",
    "15m": "15",
    "1h": "60",
    "4h": "240",
    "1d": "D",
  };
  return map[interval] || "60";
}

import type { CoinCandidate, Portfolio, StatusPayload } from "./types";

export function fmtKrw(n: number) {
  return new Intl.NumberFormat("ko-KR").format(Math.round(n));
}

export function fmtUsd(n: number, digits = 2) {
  if (n >= 1000) return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (n >= 1) return n.toLocaleString("en-US", { maximumFractionDigits: digits });
  return n.toLocaleString("en-US", { maximumFractionDigits: 6 });
}

export function fmtPct(n: number) {
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

export function isRunning(status: string) {
  return status === "running" || status === "stopping";
}

export function labelForSymbol(
  symbol: string,
  portfolio: Portfolio,
  candidates: CoinCandidate[]
): string {
  const pos = portfolio.positions.find((p) => p.symbol === symbol);
  if (pos) return pos.base;
  const c = candidates.find((x) => x.symbol === symbol);
  if (c) return c.base;
  return symbol.replace("USDT", "");
}

export function displayForSymbol(
  symbol: string,
  portfolio: Portfolio,
  candidates: CoinCandidate[]
): string {
  const pos = portfolio.positions.find((p) => p.symbol === symbol);
  if (pos) return pos.display;
  const c = candidates.find((x) => x.symbol === symbol);
  if (c) return c.display;
  const base = symbol.replace("USDT", "");
  return `${base} (${base})`;
}

/** WebSocket으로 bot 상태가 덮어쓰이지 않도록 (시작/중지 직후) */
export function mergeWsPayload(
  local: StatusPayload,
  incoming: StatusPayload,
  botLockVersion: number
): StatusPayload {
  const incomingVer = incoming.status_version ?? 0;
  if (incomingVer < botLockVersion) {
    return {
      ...incoming,
      bot: { ...incoming.bot, status: local.bot.status, message: local.bot.message },
    };
  }
  return incoming;
}

/** 최소 매수 금액 (원) — 백엔드와 동일 */
export const MIN_BUY_KRW = 5_000;

/** 차트 자동 갱신 주기 (초봉은 1초마다) */
export function chartRefreshMs(interval: string): number {
  if (interval === "1s") return 1000;
  if (interval === "1m") return 3000;
  return 12000;
}

export const DEFAULT_CONFIG = {
  trade_mode: "paper" as const,
  target_profit_krw: 2_000_000,
  initial_balance_krw: 10_000_000,
  max_positions: 0,
  stop_loss_pct: 3,
  take_profit_pct: 5,
  scan_interval_sec: 30,
  min_buy_score: 28,
  min_entry_score: 38,
  exchange: "upbit",
  api_access_key: "",
  api_secret_key: "",
  binance_api_key: "",
  binance_api_secret: "",
  use_testnet: false,
};

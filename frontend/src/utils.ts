import type { CoinCandidate, Portfolio, Position, StatusPayload } from "./types";

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

export function mergeStatus(
  prev: StatusPayload | null,
  next: StatusPayload,
  lockedView: string | null
): StatusPayload {
  if (!lockedView) return next;
  if (next.bot.view_symbol === lockedView) return next;
  return {
    ...next,
    bot: { ...next.bot, view_symbol: lockedView },
  };
}

export function findPosition(
  portfolio: Portfolio,
  symbol: string
): Position | undefined {
  return portfolio.positions.find((p) => p.symbol === symbol);
}

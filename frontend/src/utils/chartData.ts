import type { BotState, Portfolio, TradeEvent } from "../types";

export type PieSlice = {
  id: string;
  label: string;
  value: number;
  color: string;
  pct?: number;
};

export type BarItem = {
  label: string;
  value: number;
  color?: string;
};

const PALETTE = [
  "#3b9eff",
  "#22d3a5",
  "#fbbf24",
  "#a78bfa",
  "#f87171",
  "#38bdf8",
  "#fb923c",
  "#4ade80",
  "#e879f9",
  "#94a3b8",
];

export function colorForIndex(i: number): string {
  return PALETTE[i % PALETTE.length];
}

export function colorForSymbol(symbol: string): string {
  let h = 0;
  for (let i = 0; i < symbol.length; i++) {
    h = (h * 31 + symbol.charCodeAt(i)) >>> 0;
  }
  return PALETTE[h % PALETTE.length];
}

function kstHour(tsSec: number): number {
  const parts = new Intl.DateTimeFormat("ko-KR", {
    hour: "numeric",
    hour12: false,
    timeZone: "Asia/Seoul",
  }).formatToParts(new Date(tsSec * 1000));
  const h = parts.find((p) => p.type === "hour")?.value ?? "0";
  return Math.min(23, Math.max(0, parseInt(h, 10) || 0));
}

function todayKstBounds(): { start: number; end: number; label: string } {
  const dayLabel = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Seoul",
  }).format(new Date());
  const [y, m, d] = dayLabel.split("-").map(Number);
  const kstOffset = 9 * 60 * 60 * 1000;
  const start = Date.UTC(y, m - 1, d, 0, 0, 0) - kstOffset;
  const end = start + 24 * 60 * 60 * 1000;
  return { start: start / 1000, end: end / 1000, label: dayLabel };
}

export function portfolioAllocationSlices(portfolio: Portfolio): PieSlice[] {
  const slices: PieSlice[] = [];
  const cash = Math.max(0, portfolio.cash_krw || 0);
  if (cash > 0) {
    slices.push({
      id: "cash",
      label: "KRW 현금",
      value: cash,
      color: "#64748b",
    });
  }
  portfolio.positions.forEach((p, i) => {
    const val =
      (p.current_value_krw ?? 0) > 0
        ? p.current_value_krw!
        : (p.cost_basis_krw ?? 0);
    if (val <= 0) return;
    slices.push({
      id: p.symbol,
      label: p.name_ko || p.base || p.symbol.replace("USDT", ""),
      value: val,
      color: colorForSymbol(p.symbol),
    });
  });
  return withPercents(slices);
}

export function withPercents(slices: PieSlice[]): PieSlice[] {
  const total = slices.reduce((s, x) => s + x.value, 0);
  if (total <= 0) return slices;
  return slices.map((s) => ({
    ...s,
    pct: (s.value / total) * 100,
  }));
}

export function todayTradeStats(trades: TradeEvent[]) {
  const { start, end, label } = todayKstBounds();
  const day = trades.filter((t) => t.ts >= start && t.ts < end);
  const buys = day.filter((t) => (t.side || "").toUpperCase() === "BUY");
  const sells = day.filter((t) => (t.side || "").toUpperCase() === "SELL");

  let wins = 0;
  let losses = 0;
  let longS = 0;
  let scalpS = 0;
  let manualS = 0;
  for (const t of sells) {
    const r = t.reason || "";
    const o = r.toLowerCase();
    if (o.includes("단타")) scalpS++;
    else if (o.includes("롱")) longS++;
    else manualS++;
    if (r.includes("익절")) wins++;
    else if (r.includes("손절")) losses++;
  }

  const hourlyBuys = Array(24).fill(0);
  const hourlySells = Array(24).fill(0);
  for (const t of buys) hourlyBuys[kstHour(t.ts)]++;
  for (const t of sells) hourlySells[kstHour(t.ts)]++;

  return {
    dayLabel: label,
    buys: buys.length,
    sells: sells.length,
    wins,
    losses,
    longS,
    scalpS,
    manualS,
    hourlyBuys,
    hourlySells,
  };
}

export function sellOutcomeBars(
  wins: number,
  losses: number,
  totalSells: number
): BarItem[] {
  const other = Math.max(0, totalSells - wins - losses);
  const items: BarItem[] = [
    { label: "익절", value: wins, color: "#22d3a5" },
    { label: "손절", value: losses, color: "#f87171" },
  ];
  if (other > 0) {
    items.push({ label: "기타 매도", value: other, color: "#64748b" });
  }
  return items;
}

export function modeSellBars(longS: number, scalpS: number, manualS: number): BarItem[] {
  return [
    { label: "롱", value: longS, color: "#3b9eff" },
    { label: "단타", value: scalpS, color: "#fbbf24" },
    { label: "수동", value: manualS, color: "#94a3b8" },
  ];
}

export function btMaturityPct(bot: BotState): number {
  return bot.backtest?.learning?.data_maturity_pct ?? 0;
}

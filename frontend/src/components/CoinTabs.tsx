import type { CoinCandidate, Portfolio } from "../types";
import { displayForSymbol, entryBadge, fmtPct, labelForSymbol } from "../utils";

type TabInfo = {
  symbol: string;
  base: string;
  display: string;
  held: boolean;
  pnlPct?: number;
  entry: ReturnType<typeof entryBadge>;
};

type Props = {
  tabs: string[];
  selected: string;
  portfolio: Portfolio;
  candidates: CoinCandidate[];
  onSelect: (symbol: string) => void;
};

export default function CoinTabs({
  tabs,
  selected,
  portfolio,
  candidates,
  onSelect,
}: Props) {
  const candMap = new Map(candidates.map((c) => [c.symbol, c]));

  const items: TabInfo[] = tabs.map((symbol) => {
    const pos = portfolio.positions.find((p) => p.symbol === symbol);
    const cand = candMap.get(symbol);
    return {
      symbol,
      base: labelForSymbol(symbol, portfolio, candidates),
      display: displayForSymbol(symbol, portfolio, candidates),
      held: !!pos,
      pnlPct: pos?.pnl_pct,
      entry: entryBadge(cand),
    };
  });

  if (!items.some((t) => t.symbol === selected)) {
    const cand = candMap.get(selected);
    items.unshift({
      symbol: selected,
      base: labelForSymbol(selected, portfolio, candidates),
      display: displayForSymbol(selected, portfolio, candidates),
      held: !!portfolio.positions.find((p) => p.symbol === selected),
      pnlPct: portfolio.positions.find((p) => p.symbol === selected)?.pnl_pct,
      entry: entryBadge(cand),
    });
  }

  return (
    <div className="coin-tabs-wrap">
      <span className="coin-tabs-count">{items.length}종</span>
      <div className="coin-tabs" role="tablist" aria-label="코인 선택">
        {items.map((t) => (
          <button
            key={t.symbol}
            type="button"
            role="tab"
            aria-selected={selected === t.symbol}
            className={`coin-tab ${selected === t.symbol ? "active" : ""} ${t.held ? "held" : ""}`}
            onClick={() => onSelect(t.symbol)}
            title={
              t.entry.label
                ? `${t.display} · ${t.entry.label}`
                : t.display
            }
          >
            <span className="tab-base">{t.base}</span>
            {t.entry.kind !== "none" && (
              <span className={`tab-entry ${t.entry.kind}`}>{t.entry.label}</span>
            )}
            {t.held && t.pnlPct !== undefined && (
              <span className={`tab-pnl ${t.pnlPct >= 0 ? "up" : "down"}`}>
                {fmtPct(t.pnlPct)}
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

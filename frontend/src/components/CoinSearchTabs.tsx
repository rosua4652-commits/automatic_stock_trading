import { useMemo, useState } from "react";
import type { CoinCandidate, Portfolio } from "../types";
import { matchCoinSearch, resolveCoinMeta } from "../utils";
import CoinCell from "./CoinCell";

type Props = {
  tabs: string[];
  selected: string;
  portfolio: Portfolio;
  candidates: CoinCandidate[];
  onSelect: (symbol: string) => void;
};

export default function CoinSearchTabs({
  tabs,
  selected,
  portfolio,
  candidates,
  onSelect,
}: Props) {
  const [query, setQuery] = useState("");
  const candMap = useMemo(
    () => new Map(candidates.map((c) => [c.symbol, c])),
    [candidates]
  );

  const filtered = useMemo(() => {
    const list = tabs.filter((sym) =>
      matchCoinSearch(query, sym, portfolio, candidates)
    );
    if (selected && !list.includes(selected)) {
      if (matchCoinSearch(query, selected, portfolio, candidates)) {
        return [selected, ...list];
      }
    }
    return list;
  }, [tabs, query, portfolio, candidates, selected]);

  return (
    <div className="coin-search-tabs">
      <div className="coin-search-bar">
        <input
          type="search"
          className="coin-search-input"
          placeholder="코인 검색 (이름·심볼, 예: 비트코인, BTC)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="코인 검색"
        />
        <span className="coin-tabs-count">
          {filtered.length}/{tabs.length}종
        </span>
      </div>

      {query.trim() && (
        <ul className="coin-search-results" role="listbox" aria-label="검색 결과">
          {filtered.length === 0 ? (
            <li className="empty">검색 결과 없음</li>
          ) : (
            filtered.slice(0, 40).map((sym) => {
              const meta = resolveCoinMeta(sym, portfolio, candidates);
              return (
                <li key={sym}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={selected === sym}
                    className={`coin-search-item ${selected === sym ? "active" : ""}`}
                    onClick={() => onSelect(sym)}
                  >
                    <CoinCell
                      name_ko={meta.name_ko}
                      base={meta.base}
                      candidate={candMap.get(sym)}
                      held={!!portfolio.positions.find((p) => p.symbol === sym)}
                    />
                  </button>
                </li>
              );
            })
          )}
        </ul>
      )}

      <div className="coin-tabs" role="tablist" aria-label="코인 빠른 선택">
        {filtered.slice(0, query.trim() ? 30 : 80).map((sym) => {
          const meta = resolveCoinMeta(sym, portfolio, candidates);
          return (
            <button
              key={sym}
              type="button"
              role="tab"
              aria-selected={selected === sym}
              className={`coin-tab coin-tab-rich ${selected === sym ? "active" : ""}`}
              onClick={() => onSelect(sym)}
            >
              <span className="coin-tab-name">{meta.name_ko}</span>
              <span className="coin-tab-base">{meta.base}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

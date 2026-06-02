import type { CoinCandidate, Portfolio, TradeEvent } from "../types";
import { fmtKrw, fmtPct, fmtQty, resolveEntryTier, tradeAmountKrw, tradeQuantity } from "../utils";
import CoinCell from "./CoinCell";
import SurgeTagBadge from "./SurgeTagBadge";

type Props = {
  portfolio: Portfolio;
  candidates: CoinCandidate[];
  trades: TradeEvent[];
  selected: string;
  surgeTags?: Record<string, string>;
  onSelect: (symbol: string) => void;
  canTrade: boolean;
  busy: boolean;
  onQuickBuy: (symbol: string) => void;
  onSellAll?: () => void;
};

export default function PortfolioPanel({
  portfolio,
  candidates,
  trades,
  selected,
  surgeTags,
  onSelect,
  canTrade,
  busy,
  onQuickBuy,
  onSellAll,
}: Props) {
  const pnl = portfolio.unrealized_pnl_krw + portfolio.realized_pnl_krw;
  const pnlClass = pnl >= 0 ? "up" : "down";
  const candMap = new Map(candidates.map((c) => [c.symbol, c]));

  return (
    <div className="portfolio-panel">
      <section className="panel-block">
        <h3>포트폴리오</h3>
        <div className="stat-grid">
          <div className="stat">
            <span className="label">총 자산</span>
            <span className="value">{fmtKrw(portfolio.total_value_krw)}원</span>
          </div>
          <div className="stat">
            <span className="label">수익</span>
            <span className={`value ${pnlClass}`}>
              {pnl >= 0 ? "+" : ""}
              {fmtKrw(pnl)}원
            </span>
          </div>
          <div className="stat">
            <span className="label">현금</span>
            <span className="value dim">{fmtKrw(portfolio.cash_krw)}원</span>
          </div>
        </div>
        <div className="progress-wrap">
          <div className="progress-meta">
            <span>목표 달성</span>
            <span>{portfolio.progress_pct.toFixed(0)}%</span>
          </div>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${Math.min(100, portfolio.progress_pct)}%` }}
            />
          </div>
        </div>
      </section>

      <section className="panel-block">
        <div className="panel-block-head">
          <h3>보유 코인</h3>
          {portfolio.positions.length > 0 && canTrade && onSellAll && (
            <button
              type="button"
              className="btn-sell-all"
              disabled={busy}
              onClick={onSellAll}
            >
              전체 매도
            </button>
          )}
        </div>
        {portfolio.positions.length === 0 ? (
          <p className="empty">보유 중인 코인이 없습니다</p>
        ) : (
          <ul className="position-list">
            {portfolio.positions.map((p) => {
              const tier = resolveEntryTier(p);
              return (
              <li key={p.symbol}>
                <button
                  type="button"
                  className={`pos-row pos-row-rich ${selected === p.symbol ? "active" : ""}`}
                  onClick={() => onSelect(p.symbol)}
                >
                  <CoinCell
                    name_ko={p.name_ko}
                    base={p.base}
                    candidate={candMap.get(p.symbol)}
                    held
                    trailing={
                      <div className="pos-pnl-block">
                        <SurgeTagBadge symbol={p.symbol} surgeTags={surgeTags} />
                        {tier.kind === "moonshot" && (
                          <span className="pos-tier-badge moonshot">{tier.label}</span>
                        )}
                        {tier.kind === "scalp" && (
                          <span className="pos-tier-badge scalp">{tier.label}</span>
                        )}
                        <span className="pos-principal">
                          원금 {fmtKrw(p.cost_basis_krw)}원
                        </span>
                        <span
                          className={`pos-pnl-val ${p.pnl_krw >= 0 ? "up" : "down"}`}
                        >
                          {p.pnl_krw >= 0 ? "+" : ""}
                          {fmtKrw(p.pnl_krw)}원 ({fmtPct(p.pnl_pct)})
                        </span>
                      </div>
                    }
                  />
                </button>
              </li>
            );
            })}
          </ul>
        )}
      </section>

      <section className="panel-block scroll">
        <h3>분석 코인</h3>
        <p className="panel-hint">이름 / 심볼 / 진입 판단</p>
        {candidates.length === 0 ? (
          <p className="empty">「분석 시작」 후 표시됩니다</p>
        ) : (
          <ul className="candidate-list">
            {candidates.slice(0, 40).map((c) => (
              <li key={c.symbol} className="cand-item">
                <button
                  type="button"
                  className={`cand-row cand-row-rich ${selected === c.symbol ? "active" : ""}`}
                  onClick={() => onSelect(c.symbol)}
                >
                  <CoinCell
                    name_ko={c.name_ko}
                    base={c.base}
                    candidate={c}
                    trailing={
                      <span className="cand-score">{c.score}점</span>
                    }
                  />
                </button>
                {c.entry_detail && (
                  <p className="cand-detail">{c.entry_detail}</p>
                )}
                {canTrade && (
                  <button
                    type="button"
                    className="cand-buy-btn"
                    disabled={busy}
                    onClick={() => onQuickBuy(c.symbol)}
                  >
                    이 코인 매수
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {trades.length > 0 && (
        <section className="panel-block scroll">
          <h3>최근 체결</h3>
          <ul className="trade-list">
            {trades
              .slice()
              .reverse()
              .slice(0, 12)
              .map((t, i) => (
                <li
                  key={`${t.ts}-${t.symbol}-${i}`}
                  className={t.side === "BUY" ? "buy" : "sell"}
                >
                  <div className="trade-left">
                    <span className="trade-name">{t.display}</span>
                    <span className="trade-side">
                      {t.side === "BUY" ? "매수" : "매도"} ·{" "}
                      {fmtQty(tradeQuantity(t))} · {fmtKrw(tradeAmountKrw(t))}원
                    </span>
                  </div>
                  <span className="trade-reason">{t.reason}</span>
                </li>
              ))}
          </ul>
        </section>
      )}
    </div>
  );
}

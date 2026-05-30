import type { CoinCandidate, Portfolio, TradeEvent } from "../types";
import { fmtKrw, fmtPct } from "../utils";

type Props = {
  portfolio: Portfolio;
  candidates: CoinCandidate[];
  trades: TradeEvent[];
  selected: string;
  onSelect: (symbol: string) => void;
  canTrade: boolean;
  busy: boolean;
  onQuickBuy: (symbol: string) => void;
};

export default function PortfolioPanel({
  portfolio,
  candidates,
  trades,
  selected,
  onSelect,
  canTrade,
  busy,
  onQuickBuy,
}: Props) {
  const pnl = portfolio.unrealized_pnl_krw + portfolio.realized_pnl_krw;
  const pnlClass = pnl >= 0 ? "up" : "down";

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
        <h3>보유 코인</h3>
        {portfolio.positions.length === 0 ? (
          <p className="empty">자동투자 시작 시 AI가 조건에 맞는 코인에 진입합니다</p>
        ) : (
          <ul className="position-list">
            {portfolio.positions.map((p) => (
              <li key={p.symbol}>
                <button
                  type="button"
                  className={`pos-row ${selected === p.symbol ? "active" : ""}`}
                  onClick={() => onSelect(p.symbol)}
                >
                  <div className="pos-info">
                    <span className="pos-name">{p.name_ko}</span>
                    <span className="pos-pair">{p.pair_label}</span>
                  </div>
                  <span className={`pos-pnl ${p.pnl_pct >= 0 ? "up" : "down"}`}>
                    {fmtPct(p.pnl_pct)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel-block scroll">
        <h3>AI 분석 · 진입 판단</h3>
        {candidates.length === 0 ? (
          <p className="empty">자동투자 실행 시 시장 스캔·차트 분석 결과가 표시됩니다</p>
        ) : (
          <ul className="candidate-list">
            {candidates.slice(0, 12).map((c) => (
              <li key={c.symbol} className="cand-item">
                <button
                  type="button"
                  className={`cand-row ${selected === c.symbol ? "active" : ""}`}
                  onClick={() => onSelect(c.symbol)}
                >
                  <div className="pos-info">
                    <span className="pos-name">{c.name_ko}</span>
                    <span className="pos-pair">{c.pair_label}</span>
                    <span className={`cand-tag ${c.entry_ok ? "ok" : "no"}`}>
                      {c.entry_ok ? "진입가능" : "진입보류"}
                    </span>
                  </div>
                  <span className="cand-score">{c.score}점</span>
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
                      {t.side === "BUY" ? "매수" : "매도"} · {fmtKrw(t.amount_krw)}원
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

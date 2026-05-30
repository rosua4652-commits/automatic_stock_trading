import type { CoinCandidate, Portfolio, TradeEvent } from "../types";

type Props = {
  portfolio: Portfolio;
  candidates: CoinCandidate[];
  trades: TradeEvent[];
  selected: string;
  onSelect: (symbol: string) => void;
};

function fmt(n: number) {
  return new Intl.NumberFormat("ko-KR").format(Math.round(n));
}

export default function PortfolioPanel({
  portfolio,
  candidates,
  trades,
  selected,
  onSelect,
}: Props) {
  const pnl = portfolio.unrealized_pnl_krw + portfolio.realized_pnl_krw;
  const pnlClass = pnl >= 0 ? "up" : "down";

  return (
    <aside className="side-panel">
      <section className="panel-block">
        <h3>포트폴리오</h3>
        <div className="stat-grid">
          <div className="stat">
            <span className="label">총 자산</span>
            <span className="value">{fmt(portfolio.total_value_krw)}원</span>
          </div>
          <div className="stat">
            <span className="label">수익</span>
            <span className={`value ${pnlClass}`}>
              {pnl >= 0 ? "+" : ""}
              {fmt(pnl)}원
            </span>
          </div>
          <div className="stat">
            <span className="label">현금</span>
            <span className="value dim">{fmt(portfolio.cash_krw)}원</span>
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
        <h3>보유</h3>
        {portfolio.positions.length === 0 ? (
          <p className="empty">자동투자 시작 시 AI가 포지션을 구성합니다</p>
        ) : (
          <ul className="position-list">
            {portfolio.positions.map((p) => (
              <li key={p.symbol}>
                <button
                  type="button"
                  className={`pos-row ${selected === p.symbol ? "active" : ""}`}
                  onClick={() => onSelect(p.symbol)}
                >
                  <span className="pos-sym">{p.symbol.replace("USDT", "")}</span>
                  <span className={`pos-pnl ${p.pnl_pct >= 0 ? "up" : "down"}`}>
                    {p.pnl_pct >= 0 ? "+" : ""}
                    {p.pnl_pct.toFixed(2)}%
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel-block scroll">
        <h3>AI 선정</h3>
        <ul className="candidate-list">
          {candidates.slice(0, 8).map((c) => (
            <li key={c.symbol}>
              <button
                type="button"
                className={`cand-row ${selected === c.symbol ? "active" : ""}`}
                onClick={() => onSelect(c.symbol)}
              >
                <span>{c.base}</span>
                <span className="cand-score">{c.score}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      {trades.length > 0 && (
        <section className="panel-block scroll">
          <h3>최근 체결</h3>
          <ul className="trade-list">
            {trades
              .slice()
              .reverse()
              .slice(0, 6)
              .map((t, i) => (
                <li key={`${t.ts}-${i}`} className={t.side === "BUY" ? "buy" : "sell"}>
                  <span>{t.symbol.replace("USDT", "")}</span>
                  <span>{t.reason}</span>
                </li>
              ))}
          </ul>
        </section>
      )}
    </aside>
  );
}

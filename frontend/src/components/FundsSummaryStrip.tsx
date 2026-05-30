import type { Portfolio } from "../types";
import { fmtKrw } from "../utils";

type Props = {
  portfolio: Portfolio;
  compact?: boolean;
};

export default function FundsSummaryStrip({ portfolio, compact }: Props) {
  const pnl = portfolio.unrealized_pnl_krw;
  const pnlClass = pnl >= 0 ? "up" : "down";

  return (
    <section
      className={`funds-summary-strip ${compact ? "compact" : ""}`}
      aria-label="자금 현황"
    >
      <h3 className="funds-strip-title">자금 현황</h3>
      <div className="funds-strip-grid">
        <div className="funds-strip-item">
          <span className="fs-label">총 자산</span>
          <strong>{fmtKrw(portfolio.total_value_krw)}원</strong>
        </div>
        <div className="funds-strip-item">
          <span className="fs-label">현금</span>
          <strong>{fmtKrw(portfolio.cash_krw)}원</strong>
        </div>
        <div className="funds-strip-item">
          <span className="fs-label">투자 원금</span>
          <strong>{fmtKrw(portfolio.principal_krw)}원</strong>
        </div>
        <div className="funds-strip-item">
          <span className="fs-label">평가 손익</span>
          <strong className={pnlClass}>
            {pnl >= 0 ? "+" : ""}
            {fmtKrw(pnl)}원
          </strong>
        </div>
        <div className="funds-strip-item">
          <span className="fs-label">실현 손익</span>
          <strong
            className={portfolio.realized_pnl_krw >= 0 ? "up" : "down"}
          >
            {fmtKrw(portfolio.realized_pnl_krw)}원
          </strong>
        </div>
        <div className="funds-strip-item">
          <span className="fs-label">목표 달성</span>
          <strong className="accent">{portfolio.progress_pct.toFixed(0)}%</strong>
        </div>
      </div>
    </section>
  );
}

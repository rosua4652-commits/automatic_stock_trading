import { useMemo } from "react";
import type { Portfolio } from "../types";
import { fmtKrw } from "../utils";
import { portfolioAllocationSlices } from "../utils/chartData";
import SvgPieChart from "./charts/SvgPieChart";

type Props = {
  portfolio: Portfolio;
};

export default function PortfolioAllocationPanel({ portfolio }: Props) {
  const slices = useMemo(
    () => portfolioAllocationSlices(portfolio),
    [portfolio]
  );
  const coinVal = portfolio.positions.reduce(
    (s, p) => s + (p.current_value_krw || p.cost_basis_krw || 0),
    0
  );

  return (
    <section className="funds-allocation-panel">
      <div className="funds-allocation-head">
        <h3>자산 현황</h3>
        <div className="funds-allocation-totals">
          <span>총 {fmtKrw(portfolio.total_value_krw)}원</span>
          <span className="dim">
            현금 {fmtKrw(portfolio.cash_krw)} · 코인 {fmtKrw(coinVal)}
          </span>
        </div>
      </div>
      <SvgPieChart slices={slices} size={220} emptyText="보유 자산 없음" />
    </section>
  );
}

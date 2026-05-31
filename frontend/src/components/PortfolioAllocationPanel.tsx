import { useMemo } from "react";
import type { Portfolio } from "../types";
import { fmtKrw } from "../utils";
import { portfolioAllocationSlices } from "../utils/chartData";
import CollapsibleSection from "./CollapsibleSection";
import SvgPieChart from "./charts/SvgPieChart";

const STORAGE_KEY = "aidi-funds-allocation-collapsed";

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

  const collapsedHint = useMemo(() => {
    if (slices.length === 0) {
      return "보유 없음 · 「펼치기」로 비율 차트";
    }
    const parts: string[] = [`총 ${fmtKrw(portfolio.total_value_krw)}원`];
    const cash = slices.find((s) => s.id === "cash");
    if (cash?.pct != null) {
      parts.push(`현금 ${cash.pct.toFixed(1)}%`);
    }
    for (const s of slices.filter((x) => x.id !== "cash").slice(0, 2)) {
      if (s.pct != null) {
        parts.push(`${s.label} ${s.pct.toFixed(1)}%`);
      }
    }
    parts.push("「펼치기」로 차트");
    return parts.join(" · ");
  }, [slices, portfolio.total_value_krw]);

  return (
    <CollapsibleSection
      title="자산 현황"
      storageKey={STORAGE_KEY}
      defaultCollapsed
      collapsedHint={collapsedHint}
      className="funds-allocation-panel"
    >
      <p className="funds-allocation-summary">
        <span>총 {fmtKrw(portfolio.total_value_krw)}원</span>
        <span className="dim">
          현금 {fmtKrw(portfolio.cash_krw)} · 코인 {fmtKrw(coinVal)}
        </span>
      </p>
      <SvgPieChart slices={slices} size={132} emptyText="보유 자산 없음" />
    </CollapsibleSection>
  );
}

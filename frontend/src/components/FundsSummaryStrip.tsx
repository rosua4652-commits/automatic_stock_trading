import type { AppConfig, Portfolio } from "../types";
import { fmtKrw } from "../utils";

type Props = {
  portfolio: Portfolio;
  config: AppConfig;
  variant?: "topbar" | "strip";
};

/** 상단 툴바 자금 현황 (목표·달성·총자산·손익 통합) */
export default function FundsSummaryStrip({
  portfolio,
  config,
  variant = "topbar",
}: Props) {
  const unrealized = portfolio.unrealized_pnl_krw;
  const realized = portfolio.realized_pnl_krw;
  const uClass = unrealized >= 0 ? "up" : "down";
  const rClass = realized >= 0 ? "up" : "down";

  const items = [
    { label: "목표", value: `${fmtKrw(config.target_profit_krw)}`, accent: false },
    {
      label: "달성",
      value: `${portfolio.progress_pct.toFixed(0)}%`,
      accent: true,
    },
    { label: "총자산", value: `${fmtKrw(portfolio.total_value_krw)}`, bold: true },
    { label: "현금", value: `${fmtKrw(portfolio.cash_krw)}`, dim: true },
    { label: "투자 원금", value: `${fmtKrw(portfolio.principal_krw)}` },
    {
      label: "평가 손익",
      value: `${unrealized >= 0 ? "+" : ""}${fmtKrw(unrealized)}`,
      className: uClass,
    },
    {
      label: "실현 손익",
      value: `${realized >= 0 ? "+" : ""}${fmtKrw(realized)}`,
      className: rClass,
    },
  ];

  if (variant === "topbar") {
    return (
      <div className="funds-topbar" aria-label="자금 현황">
        {items.map((it) => (
          <div key={it.label} className="funds-topbar-item">
            <span className="ft-label">{it.label}</span>
            <strong
              className={`ft-value ${it.accent ? "accent" : ""} ${it.dim ? "dim" : ""} ${it.bold ? "" : ""} ${it.className ?? ""}`}
            >
              {it.value}
            </strong>
          </div>
        ))}
      </div>
    );
  }

  return (
    <section className="funds-summary-strip" aria-label="자금 현황">
      <h3 className="funds-strip-title">자금 현황</h3>
      <div className="funds-strip-grid">
        {items.map((it) => (
          <div key={it.label} className="funds-strip-item">
            <span className="fs-label">{it.label}</span>
            <strong className={it.className}>{it.value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

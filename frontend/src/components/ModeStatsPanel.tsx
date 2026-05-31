import { fmtKrw, fmtPct } from "../utils";

export type ModeStatsData = {
  mode: string;
  total_value_krw: number;
  cash_krw: number;
  coin_value_krw: number;
  daily_pnl_krw: number;
  daily_pnl_pct: number;
  positions_count: number;
  report?: {
    buys_count?: number;
    sells_count?: number;
  };
};

type Props = {
  title: string;
  data: ModeStatsData;
  active?: boolean;
  hint?: string;
};

export default function ModeStatsPanel({
  title,
  data,
  active,
  hint,
}: Props) {
  const pnlTone = data.daily_pnl_krw >= 0 ? "up" : "down";
  const buys = Number(data.report?.buys_count ?? 0);
  const sells = Number(data.report?.sells_count ?? 0);

  return (
    <section
      className={`stats-mode-col${active ? " is-active" : ""}`}
      aria-label={title}
    >
      <h3 className="stats-mode-title">
        {title}
        {active && <span className="stats-mode-badge">선택 중</span>}
      </h3>
      {hint && <p className="stats-mode-hint">{hint}</p>}
      <div className="stats-mode-metrics">
        <div className="stats-mode-metric">
          <span className="stats-mode-label">총자산</span>
          <span className="stats-mode-value">{fmtKrw(data.total_value_krw)}원</span>
          <span className="stats-mode-sub">
            현금 {fmtKrw(data.cash_krw)} · 코인 {fmtKrw(data.coin_value_krw)}
          </span>
        </div>
        <div className={`stats-mode-metric tone-${pnlTone}`}>
          <span className="stats-mode-label">당일 손익</span>
          <span className="stats-mode-value">
            {data.daily_pnl_krw >= 0 ? "+" : ""}
            {fmtKrw(data.daily_pnl_krw)}원
          </span>
          <span className="stats-mode-sub">{fmtPct(data.daily_pnl_pct)}</span>
        </div>
        <div className="stats-mode-metric">
          <span className="stats-mode-label">보유 · 당일 매매</span>
          <span className="stats-mode-value">{data.positions_count}종</span>
          <span className="stats-mode-sub">
            매수 {buys} / 매도 {sells}
          </span>
        </div>
      </div>
    </section>
  );
}

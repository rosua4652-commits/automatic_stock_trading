import { useEffect, useMemo, useState } from "react";
import { dailyReportCsvUrl, fetchDailyReport } from "../api";
import type { BotState, Portfolio, TradeEvent } from "../types";
import { fmtKrw, fmtPct } from "../utils";
import {
  modeSellBars,
  portfolioAllocationSlices,
  sellOutcomeBars,
  todayTradeStats,
  btMaturityPct,
  withPercents,
} from "../utils/chartData";
import BarChart from "./charts/BarChart";
import HourlyActivityChart from "./charts/HourlyActivityChart";
import KpiCard from "./charts/KpiCard";
import SvgPieChart from "./charts/SvgPieChart";
import AutoInvestDashboard from "./AutoInvestDashboard";

type Props = {
  portfolio: Portfolio;
  trades: TradeEvent[];
  bot: BotState;
  configMode: string;
};

export default function StatsTab({ portfolio, trades, bot, configMode }: Props) {
  const [report, setReport] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    fetchDailyReport()
      .then((r) => setReport(r.report))
      .catch(() => setReport(null));
  }, [portfolio.total_value_krw, trades.length, bot.last_scan]);

  const day = useMemo(() => todayTradeStats(trades), [trades]);
  const alloc = useMemo(() => portfolioAllocationSlices(portfolio), [portfolio]);

  const dailyPnl = Number(report?.daily_pnl_krw ?? 0);
  const dailyPct = Number(report?.daily_pnl_pct ?? 0);
  const pnlTone = dailyPnl >= 0 ? "up" : "down";

  const tradeMixSlices = useMemo(
    () =>
      withPercents(
        [
          { id: "buy", label: "매수", value: day.buys, color: "#3b9eff" },
          { id: "sell", label: "매도", value: day.sells, color: "#f87171" },
        ].filter((s) => s.value > 0)
      ),
    [day.buys, day.sells]
  );

  const btM = btMaturityPct(bot);

  return (
    <div className="stats-tab scroll-y">
      <header className="stats-tab-head">
        <h2>통계 · 대시보드</h2>
        <p className="panel-hint">
          {day.dayLabel} (KST) · {configMode === "live" ? "실거래" : "모의투자"}
        </p>
        <a className="link-btn" href={dailyReportCsvUrl()} download>
          당일 CSV
        </a>
      </header>

      <div className="kpi-grid">
        <KpiCard
          label="당일 손익"
          value={`${dailyPnl >= 0 ? "+" : ""}${fmtKrw(dailyPnl)}원`}
          sub={fmtPct(dailyPct)}
          tone={pnlTone}
        />
        <KpiCard
          label="총자산"
          value={`${fmtKrw(portfolio.total_value_krw)}원`}
          sub={`현금 ${fmtKrw(portfolio.cash_krw)}`}
        />
        <KpiCard
          label="당일 매매"
          value={`${day.buys} / ${day.sells}`}
          sub="매수 / 매도"
        />
        <KpiCard
          label="익절·손절"
          value={`${day.wins} / ${day.losses}`}
          sub={
            day.sells > 0
              ? `승률 ${((day.wins / day.sells) * 100).toFixed(0)}%`
              : "매도 없음"
          }
          tone={day.wins >= day.losses ? "up" : "down"}
        />
        <KpiCard
          label="BT 성숙도"
          value={`${btM.toFixed(0)}%`}
          sub={`롱≥${bot.backtest?.learning?.long_min_bt_score?.toFixed(0) ?? "—"} 단타≥${bot.backtest?.learning?.scalp_min_bt_score?.toFixed(0) ?? "—"}`}
        />
        <KpiCard
          label="보유 종목"
          value={`${portfolio.positions.length}종`}
          sub={`평가 ${fmtKrw(
            portfolio.positions.reduce(
              (s, p) => s + (p.current_value_krw || 0),
              0
            )
          )}원`}
        />
      </div>

      <div className="stats-chart-grid">
        <section className="stats-chart-card wide">
          <HourlyActivityChart
            buys={day.hourlyBuys}
            sells={day.hourlySells}
            title="시간대별 매매 (KST)"
          />
        </section>

        <section className="stats-chart-card">
          <SvgPieChart
            slices={alloc}
            title="자산 배분 (현재)"
            emptyText="보유 없음 · 현금만"
          />
        </section>

        <section className="stats-chart-card">
          <SvgPieChart
            slices={tradeMixSlices}
            title="당일 매수 vs 매도"
            emptyText="당일 체결 없음"
          />
        </section>

        <section className="stats-chart-card">
          <BarChart
            title="매도 유형 (롱/단타/수동)"
            items={modeSellBars(day.longS, day.scalpS, day.manualS)}
            maxValue={Math.max(1, day.sells)}
          />
        </section>

        <section className="stats-chart-card">
          <BarChart
            title="매도 결과"
            items={sellOutcomeBars(day.wins, day.losses, day.sells)}
            maxValue={Math.max(1, day.sells)}
          />
        </section>

        <section className="stats-chart-card">
          <BarChart
            title="BT 학습 성숙도"
            items={[{ label: "성숙 %", value: btM, color: "#3b9eff" }]}
            maxValue={100}
            unit="%"
          />
        </section>
      </div>

      <AutoInvestDashboard bot={bot} />
    </div>
  );
}

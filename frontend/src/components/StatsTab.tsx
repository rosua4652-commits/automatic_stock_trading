import { useEffect, useMemo, useState } from "react";
import { backtestReportCsvUrl, dailyReportCsvUrl, fetchStatsOverview } from "../api";
import type { BotState, Portfolio, TradeEvent } from "../types";
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
import ModeStatsPanel, { type ModeStatsData } from "./ModeStatsPanel";

type Props = {
  portfolio: Portfolio;
  trades: TradeEvent[];
  bot: BotState;
  configMode: string;
};

type Overview = {
  active_mode: string;
  day_kst?: string;
  paper: ModeStatsData & { portfolio?: Portfolio; trades?: TradeEvent[] };
  live: ModeStatsData & { portfolio?: Portfolio; trades?: TradeEvent[] };
  live_linked?: boolean;
};

function portfolioFromBlock(
  block: Overview["paper"] | undefined,
  fallback: Portfolio
): Portfolio {
  if (block?.portfolio && typeof block.portfolio === "object") {
    return block.portfolio as Portfolio;
  }
  return fallback;
}

export default function StatsTab({ portfolio, trades, bot, configMode }: Props) {
  const [overview, setOverview] = useState<Overview | null>(null);

  useEffect(() => {
    fetchStatsOverview()
      .then((r) => setOverview(r as Overview))
      .catch(() => setOverview(null));
  }, [portfolio.total_value_krw, trades.length, bot.last_scan, configMode]);

  const activeKey = overview?.active_mode ?? configMode;
  const activeBlock =
    activeKey === "live" ? overview?.live : overview?.paper;
  const chartTrades = activeBlock?.trades ?? trades;
  const chartPortfolio = portfolioFromBlock(activeBlock, portfolio);

  const day = useMemo(() => todayTradeStats(chartTrades), [chartTrades]);
  const paperAlloc = useMemo(
    () =>
      portfolioAllocationSlices(
        portfolioFromBlock(overview?.paper, portfolio)
      ),
    [overview?.paper, portfolio]
  );
  const liveAlloc = useMemo(
    () =>
      portfolioAllocationSlices(
        portfolioFromBlock(overview?.live, { ...portfolio, positions: [], cash_krw: 0, total_value_krw: 0 })
      ),
    [overview?.live, portfolio]
  );

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
  const dayLabel = overview?.day_kst ?? day.dayLabel;

  const paperData: ModeStatsData = overview?.paper ?? {
    mode: "paper",
    total_value_krw: configMode === "paper" ? portfolio.total_value_krw : 0,
    cash_krw: configMode === "paper" ? portfolio.cash_krw : 0,
    coin_value_krw: 0,
    daily_pnl_krw: 0,
    daily_pnl_pct: 0,
    positions_count: configMode === "paper" ? portfolio.positions.length : 0,
  };

  const liveData: ModeStatsData = overview?.live ?? {
    mode: "live",
    total_value_krw: configMode === "live" ? portfolio.total_value_krw : 0,
    cash_krw: configMode === "live" ? portfolio.cash_krw : 0,
    coin_value_krw: 0,
    daily_pnl_krw: 0,
    daily_pnl_pct: 0,
    positions_count: configMode === "live" ? portfolio.positions.length : 0,
  };

  return (
    <div className="stats-tab scroll-y">
      <header className="stats-tab-head">
        <h2>통계 · 대시보드</h2>
        <p className="panel-hint">{dayLabel} (KST) · 모의 / 실거래 분리</p>
        <div className="stats-tab-dl-links">
          <a
            className="link-btn"
            href={dailyReportCsvUrl(activeKey)}
            download
          >
            당일 CSV ({activeKey === "live" ? "실거래" : "모의"})
          </a>
          <a className="link-btn" href={backtestReportCsvUrl()} download>
            백테스트 CSV
          </a>
        </div>
      </header>

      <div className="stats-mode-split">
        <ModeStatsPanel
          title="모의투자"
          data={paperData}
          active={activeKey === "paper"}
        />
        <ModeStatsPanel
          title="실거래"
          data={liveData}
          active={activeKey === "live"}
          hint={
            overview && !overview.live_linked
              ? "API 미연결 — 키 저장 후 연결 테스트"
              : undefined
          }
        />
      </div>

      <p className="stats-tab-hint">
        아래 차트 · 당일 체결 분석:{" "}
        <strong>{activeKey === "live" ? "실거래" : "모의투자"}</strong> (상단
        「선택 중」 모드)
      </p>

      <div className="kpi-grid kpi-grid-compact">
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
      </div>

      <div className="stats-chart-grid">
        <section className="stats-chart-card wide">
          <HourlyActivityChart
            buys={day.hourlyBuys}
            sells={day.hourlySells}
            title={`시간대별 매매 (KST) · ${activeKey === "live" ? "실거래" : "모의"}`}
          />
        </section>

        <section className="stats-chart-card">
          <SvgPieChart
            slices={paperAlloc}
            title="자산 배분 · 모의"
            emptyText="모의 보유 없음"
          />
        </section>

        <section className="stats-chart-card">
          <SvgPieChart
            slices={liveAlloc}
            title="자산 배분 · 실거래"
            emptyText="실거래 보유 없음"
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

import { useEffect, useState } from "react";
import { dailyReportCsvUrl, fetchDailyReport } from "../api";
import { fmtKrw } from "../utils";

export default function DailyReportPanel() {
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    fetchDailyReport()
      .then((r) => setReport(r.report))
      .catch((e) => setErr(e instanceof Error ? e.message : "로드 실패"));
  }, []);

  if (err) {
    return <p className="panel-hint warn">{err}</p>;
  }
  if (!report) {
    return <p className="panel-hint">일일 리포트 불러오는 중…</p>;
  }

  return (
    <section className="report-panel daily-report">
      <div className="report-panel-head">
        <h3>오늘 요약 ({String(report.day_kst)})</h3>
        <a className="link-btn" href={dailyReportCsvUrl()} download>
          CSV
        </a>
      </div>
      <div className="report-grid">
        <div>
          <span className="fg-label">당일 손익</span>
          <span>
            {fmtKrw(Number(report.daily_pnl_krw))}원 (
            {Number(report.daily_pnl_pct).toFixed(2)}%)
          </span>
        </div>
        <div>
          <span className="fg-label">매수/매도</span>
          <span>
            {Number(report.buys_count)} / {Number(report.sells_count)}
          </span>
        </div>
        <div>
          <span className="fg-label">승률(익절·손절 기준)</span>
          <span>
            {Number(report.win_rate_pct)}% ({Number(report.wins)}승{" "}
            {Number(report.losses)}패)
          </span>
        </div>
        <div>
          <span className="fg-label">롱/단타/수동 매도</span>
          <span>
            {Number(report.long_sells)} / {Number(report.scalp_sells)} /{" "}
            {Number(report.manual_sells)}
          </span>
        </div>
        <div>
          <span className="fg-label">보유 종목</span>
          <span>{Number(report.open_positions)}</span>
        </div>
        {report.kill_switch ? (
          <div className="report-kill">
            킬 스위치: {String(report.kill_reason)}
          </div>
        ) : null}
      </div>
    </section>
  );
}

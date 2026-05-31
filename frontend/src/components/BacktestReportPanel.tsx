import { useEffect, useState } from "react";
import { fetchBacktestReport } from "../api";

export default function BacktestReportPanel() {
  const [report, setReport] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    fetchBacktestReport().then((r) => setReport(r.report)).catch(() => setReport(null));
  }, []);

  if (!report) {
    return <p className="panel-hint">백테스트 리포트 불러오는 중…</p>;
  }

  const top = (report.top_symbols as Array<Record<string, unknown>>) || [];
  const disclaimer = String(report.disclaimer || "");

  return (
    <section className="report-panel backtest-report">
      <h3>백테스트 리포트</h3>
      <p className="panel-hint warn">{disclaimer}</p>
      <p className="panel-hint">
        BT 성숙 {Number(report.data_maturity_pct).toFixed(0)}% · 롱≥
        {Number(report.long_min_bt_score)} 단타≥
        {Number(report.scalp_min_bt_score)} · 종목 {Number(report.symbols_in_store)}
      </p>
      <div className="bt-report-table-wrap">
        <table className="bt-report-table">
          <thead>
            <tr>
              <th>종목</th>
              <th>유형</th>
              <th>점수</th>
              <th>승률</th>
              <th>건수</th>
              <th>손/익%</th>
            </tr>
          </thead>
          <tbody>
            {top.map((row) => (
              <tr key={`${row.symbol}-${row.mode}`}>
                <td>{String(row.symbol).replace("USDT", "")}</td>
                <td>{String(row.mode)}</td>
                <td>{Number(row.score).toFixed(0)}</td>
                <td>{Number(row.win_rate_pct).toFixed(0)}%</td>
                <td>{Number(row.trades)}</td>
                <td>
                  {Number(row.best_sl_pct)}/{Number(row.best_tp_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

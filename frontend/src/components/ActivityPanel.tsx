import type { ActivityEntry, BotState } from "../types";
import { isRunning } from "../utils";

function fmtTime(ts: number): string {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

type Props = {
  bot: BotState;
};

export default function ActivityPanel({ bot }: Props) {
  const running = isRunning(bot.status);
  const logs = bot.activity_log ?? [];

  if (!running && logs.length === 0) {
    return null;
  }

  return (
    <section className="activity-panel">
      <div className="activity-head">
        <h3 className="activity-title">진행 · 로그</h3>
        {running && (bot.seconds_until_scan ?? 0) > 0 && (
          <span className="activity-countdown">
            다음 스캔 {bot.seconds_until_scan}초
          </span>
        )}
        {bot.phase && running && (
          <span className="activity-phase">{bot.phase_detail || bot.phase}</span>
        )}
      </div>
      {bot.ai_settings_summary && (
        <p className="activity-ai-summary">{bot.ai_settings_summary}</p>
      )}
      {bot.auto_invest_message && (
        <p className="activity-auto-msg">{bot.auto_invest_message}</p>
      )}
      {bot.backtest?.message && (
        <p className="activity-bt-msg">BT: {bot.backtest.message}</p>
      )}
      <ul className="activity-list">
        {logs.length === 0 ? (
          <li className="activity-item muted">스캔·자동매수 단계가 여기 표시됩니다</li>
        ) : (
          logs.slice(0, 20).map((e, i) => (
            <ActivityLine key={`${e.ts}-${i}`} entry={e} />
          ))
        )}
      </ul>
      <p className="activity-hint">
        파일 로그: run-log.bat · logs-aidi.bat · logs\aidi-server.log
      </p>
    </section>
  );
}

function ActivityLine({ entry }: { entry: ActivityEntry }) {
  const cls =
    entry.level === "warn"
      ? "warn"
      : entry.level === "ok"
        ? "ok"
        : "info";
  return (
    <li className={`activity-item ${cls}`}>
      <span className="activity-ts">{fmtTime(entry.ts)}</span>
      <span className="activity-phase-tag">[{entry.phase}]</span>
      <span className="activity-text">{entry.message}</span>
    </li>
  );
}

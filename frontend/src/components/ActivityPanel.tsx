import { useCallback, useState } from "react";
import type { ActivityEntry, BotState } from "../types";
import { isRunning } from "../utils";

const COLLAPSED_LINES = 3;
const STORAGE_KEY = "aidi-activity-collapsed";

function readCollapsedPref(): boolean {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "1") return true;
    if (v === "0") return false;
  } catch {
    /* ignore */
  }
  return true;
}

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
  const [collapsed, setCollapsed] = useState(readCollapsedPref);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  if (!running && logs.length === 0) {
    return null;
  }

  const visibleLogs = logs.slice(0, collapsed ? COLLAPSED_LINES : 20);

  return (
    <section
      className={`activity-panel${collapsed ? " is-collapsed" : ""}`}
    >
      <button
        type="button"
        className="activity-panel-toggle"
        onClick={toggleCollapsed}
        aria-expanded={!collapsed}
        title={collapsed ? "로그 펼치기" : "로그 접기"}
      >
        <span className="activity-chevron" aria-hidden>
          {collapsed ? "▶" : "▼"}
        </span>
        <span className="activity-title">진행 · 로그</span>
        {running && (bot.seconds_until_scan ?? 0) > 0 && (
          <span className="activity-countdown">
            다음 스캔 {bot.seconds_until_scan}초
          </span>
        )}
        {bot.phase && running && !collapsed && (
          <span className="activity-phase">{bot.phase_detail || bot.phase}</span>
        )}
        <span className="activity-toggle-pill">
          {collapsed ? "펼치기" : "접기"}
        </span>
      </button>

      {!collapsed && bot.ai_settings_summary && (
        <p className="activity-ai-summary">{bot.ai_settings_summary}</p>
      )}
      {!collapsed && bot.auto_invest_message && (
        <p className="activity-auto-msg">{bot.auto_invest_message}</p>
      )}
      {!collapsed && bot.backtest?.message && (
        <p className="activity-bt-msg">BT: {bot.backtest.message}</p>
      )}
      <ul className="activity-list">
        {visibleLogs.length === 0 ? (
          <li className="activity-item muted">스캔·자동매수 단계가 여기 표시됩니다</li>
        ) : (
          visibleLogs.map((e, i) => (
            <ActivityLine key={`${e.ts}-${i}`} entry={e} />
          ))
        )}
      </ul>
      {collapsed && logs.length > COLLAPSED_LINES && (
        <p className="activity-more-hint">
          최근 {COLLAPSED_LINES}줄 · 전체 {logs.length}줄 — 위 「펼치기」 클릭
        </p>
      )}
      {!collapsed && (
        <p className="activity-hint">
          파일 로그: run-log.bat · logs-aidi.bat · logs\aidi-server.log
        </p>
      )}
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

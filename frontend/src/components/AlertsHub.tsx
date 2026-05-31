import { useCallback, useState } from "react";
import type { ApplyItem, EditableRecommendation } from "../hooks/useRecommendationAmounts";
import type { BacktestStatus, DirectionSignalItem } from "../types";
import { fmtUsd, isRunning } from "../utils";
import ActivityPanel from "./ActivityPanel";
import EntryAlertsPanel from "./EntryAlertsPanel";
import type { BotState } from "../types";

type Props = {
  recommendations: EditableRecommendation[];
  longSignals: DirectionSignalItem[];
  shortSignals: DirectionSignalItem[];
  directionMessage?: string;
  backtestMessage?: string;
  backtest?: BacktestStatus;
  autoInvestMessage?: string;
  bot: BotState;
  botStatus: string;
  cashKrw: number;
  feePct?: number;
  busy: boolean;
  onApplyRecs: (items: ApplyItem[]) => Promise<void>;
  onScanDirection: (side: "long" | "short") => Promise<void>;
  onOpenChart: () => void;
  onSelectSymbol: (symbol: string) => void;
};

export default function AlertsHub({
  recommendations,
  longSignals,
  shortSignals,
  directionMessage,
  backtestMessage,
  backtest,
  autoInvestMessage,
  bot,
  botStatus,
  cashKrw,
  feePct = 0.05,
  busy,
  onApplyRecs,
  onScanDirection,
  onOpenChart,
  onSelectSymbol,
}: Props) {
  const running = isRunning(botStatus);
  const [dismissedRec, setDismissedRec] = useState<Set<string>>(() => new Set());
  const [dismissedLong, setDismissedLong] = useState<Set<string>>(() => new Set());
  const [dismissedShort, setDismissedShort] = useState<Set<string>>(() => new Set());
  const [scanBusy, setScanBusy] = useState<"long" | "short" | null>(null);

  const visibleRecs = recommendations.filter((r) => !dismissedRec.has(r.symbol));
  const visibleLong = longSignals.filter((s) => !dismissedLong.has(s.signal_id));
  const visibleShort = shortSignals.filter((s) => !dismissedShort.has(s.signal_id));

  const runScan = useCallback(
    async (side: "long" | "short") => {
      setScanBusy(side);
      try {
        await onScanDirection(side);
      } finally {
        setScanBusy(null);
      }
    },
    [onScanDirection]
  );

  return (
    <div className="alerts-hub">
      <ActivityPanel bot={bot} />
      {autoInvestMessage && (
        <p className="auto-invest-banner">{autoInvestMessage}</p>
      )}
      <section className="alerts-hub-section alerts-hub-recs">
        <div className="alerts-hub-section-head">
          <h2 className="alerts-hub-title">투자 제안</h2>
          <p className="panel-hint">
            분석 시작=제안만 · 자동 투자 시작=롱/단타 체크 후 BT·학습 통과 시 자동 매수
          </p>
          {visibleRecs.length > 0 && (
            <button
              type="button"
              className="btn-ghost btn-sm"
              onClick={() => setDismissedRec(new Set(recommendations.map((r) => r.symbol)))}
            >
              제안 전체 삭제
            </button>
          )}
        </div>
        <EntryAlertsPanel
          list={visibleRecs}
          botStatus={botStatus}
          cashKrw={cashKrw}
          feePct={feePct}
          busy={busy}
          onApply={onApplyRecs}
          onOpenChart={onOpenChart}
          onSelectSymbol={onSelectSymbol}
        />
      </section>

      <section className="alerts-hub-section alerts-hub-direction">
        <div className="alerts-hub-section-head">
          <h2 className="alerts-hub-title">롱 · 숏 시그널</h2>
          <p className="panel-hint">
            일목균형표 · 이평 · 볼린저 · RSI — 버튼을 눌러 분석 (투자 제안과 별도)
          </p>
          <div className="alerts-scan-actions">
            <button
              type="button"
              className="btn-primary btn-sm"
              disabled={!!scanBusy || busy}
              onClick={() => runScan("long")}
            >
              {scanBusy === "long" ? "롱 분석 중…" : "롱 추천 분석"}
            </button>
            <button
              type="button"
              className="btn-secondary btn-sm"
              disabled={!!scanBusy || busy}
              onClick={() => runScan("short")}
            >
              {scanBusy === "short" ? "숏 분석 중…" : "숏 추천 분석"}
            </button>
          </div>
          {directionMessage && (
            <p className="alerts-scan-msg">{directionMessage}</p>
          )}
        </div>

        <DirectionBlock
          title="롱 추천"
          emptyText="롱 조건에 맞는 종목 없음 — 「롱 추천 분석」을 눌러 주세요"
          items={visibleLong}
          onDismiss={(id) => setDismissedLong((s) => new Set(s).add(id))}
          onClear={() => setDismissedLong(new Set(longSignals.map((x) => x.signal_id)))}
          onSelect={onSelectSymbol}
        />
        <DirectionBlock
          title="숏 추천"
          emptyText="숏 조건에 맞는 종목 없음 — 「숏 추천 분석」을 눌러 주세요"
          items={visibleShort}
          onDismiss={(id) => setDismissedShort((s) => new Set(s).add(id))}
          onClear={() => setDismissedShort(new Set(shortSignals.map((x) => x.signal_id)))}
          onSelect={onSelectSymbol}
        />
      </section>

      {backtestMessage && (
        <footer className="alerts-backtest-foot">
          <span className="alerts-backtest-label">백테스트</span>
          {backtestMessage}
          {backtest?.best_sl_pct ? (
            <span className="alerts-backtest-params">
              {" "}
              · 최적 손익절 {backtest.best_sl_pct}%/{backtest.best_tp_pct}%
            </span>
          ) : null}
          {backtest?.learning?.long_min_bt_score != null ? (
            <span className="alerts-backtest-params">
              {" "}
              · BT성숙 {backtest.learning.data_maturity_pct?.toFixed(0) ?? 0}% ·
              롱≥{backtest.learning.long_min_bt_score?.toFixed(0)} 단타≥
              {backtest.learning.scalp_min_bt_score?.toFixed(0)}
              {(backtest.learning.execution_feedback_count ?? 0) > 0
                ? ` · 체결 ${backtest.learning.execution_feedback_count}건 승률 ${backtest.learning.execution_win_rate?.toFixed(0)}%`
                : ""}
              {backtest.learning.last_adjust_message
                ? ` (${backtest.learning.last_adjust_message})`
                : ""}
            </span>
          ) : null}
          {autoInvestMessage ? ` · ${autoInvestMessage}` : null}
          {running && " · 분석 실행 중"}
        </footer>
      )}
    </div>
  );
}

function DirectionBlock({
  title,
  emptyText,
  items,
  onDismiss,
  onClear,
  onSelect,
}: {
  title: string;
  emptyText: string;
  items: DirectionSignalItem[];
  onDismiss: (id: string) => void;
  onClear: () => void;
  onSelect: (sym: string) => void;
}) {
  return (
    <div className="direction-block">
      <div className="direction-block-head">
        <h3>
          {title} <span className="alerts-count">{items.length}</span>
        </h3>
        {items.length > 0 && (
          <button type="button" className="btn-ghost btn-xs" onClick={onClear}>
            목록 비우기
          </button>
        )}
      </div>
      {items.length === 0 ? (
        <p className="empty direction-empty">{emptyText}</p>
      ) : (
        <ul className="direction-list">
          {items.map((s) => (
            <li key={s.signal_id} className="direction-item">
              <div className="direction-item-top">
                <button
                  type="button"
                  className="direction-item-main"
                  onClick={() => onSelect(s.symbol)}
                >
                  <span className="direction-side">{s.side === "long" ? "롱" : "숏"}</span>
                  <span className="direction-name">{s.name_ko || s.base}</span>
                  <span className="direction-score">{s.score.toFixed(0)}점</span>
                </button>
                <button
                  type="button"
                  className="btn-icon-dismiss"
                  title="알림 삭제"
                  onClick={() => onDismiss(s.signal_id)}
                >
                  ×
                </button>
              </div>
              <p className="direction-detail">{s.detail}</p>
              {s.price_usdt > 0 && (
                <p className="direction-meta">
                  ${fmtUsd(s.price_usdt)} · RSI {s.rsi} · {s.trend}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

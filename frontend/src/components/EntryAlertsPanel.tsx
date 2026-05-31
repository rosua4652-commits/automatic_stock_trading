import type { ApplyItem, EditableRecommendation } from "../hooks/useRecommendationAmounts";
import { deployableCashKrw, fmtKrw, fmtUsd, isRunning } from "../utils";

type Props = {
  list: EditableRecommendation[];
  botStatus: string;
  cashKrw: number;
  feePct?: number;
  busy: boolean;
  onApply: (items: ApplyItem[]) => Promise<void>;
  onOpenChart: () => void;
  onSelectSymbol: (symbol: string) => void;
};

/** 상단 알림 탭 — 화면 가리지 않는 진입 가능 알림 */
export default function EntryAlertsPanel({
  list,
  botStatus,
  cashKrw,
  feePct = 0.05,
  busy,
  onApply,
  onOpenChart,
  onSelectSymbol,
}: Props) {
  const running = isRunning(botStatus);
  const deployable = deployableCashKrw(cashKrw, feePct);
  const total = list.reduce((s, r) => s + r.amount_krw, 0);

  if (list.length === 0) {
    return (
      <div className="alerts-screen">
        <header className="alerts-screen-head">
          <h2>진입 알림</h2>
          <p className="panel-hint">
            {running
              ? "분석 중… 진입 가능 코인이 나오면 여기에 표시됩니다"
              : "「분석 시작」 후 진입 가능 코인이 여기에 표시됩니다"}
          </p>
        </header>
        <p className="empty alerts-empty">
          현재 알림 없음 · 「차트 · AI」 왼쪽 「투자 제안」에서도 확인할 수 있습니다
        </p>
      </div>
    );
  }

  return (
    <div className="alerts-screen">
      <header className="alerts-screen-head">
        <h2>
          진입 가능 <span className="alerts-count">{list.length}</span>종
        </h2>
        <p className="panel-hint">
          금액 조절·승인은 「차트 · AI」 왼쪽 「투자 제안」 패널에서 하세요
        </p>
        <div className="alerts-screen-actions">
          <button type="button" className="btn-ghost btn-sm" onClick={onOpenChart}>
            차트 · 투자 제안 열기
          </button>
          <button
            type="button"
            className="btn-primary btn-sm"
            disabled={busy || total > deployable + 500}
            onClick={() =>
              onApply(list.map((r) => ({ symbol: r.symbol, amount_krw: r.amount_krw })))
            }
          >
            {busy ? "매수 중…" : `전체 승인 (${list.length}건)`}
          </button>
        </div>
      </header>

      <ul className="alerts-quick-list">
        {list.map((r) => (
          <li key={r.symbol} className="alerts-quick-item">
            <button
              type="button"
              className="alerts-quick-row"
              onClick={() => onSelectSymbol(r.symbol)}
            >
              <span className="alerts-quick-name">{r.name_ko}</span>
              <span className="alerts-quick-base">{r.base}</span>
              <span className="alerts-quick-amt">{fmtKrw(r.amount_krw)}원</span>
            </button>
            <p className="alerts-quick-detail">
              {(r.stop_loss_pct ?? 0) > 0 && (
                <>
                  BT 손절 {r.stop_loss_pct?.toFixed(1)}% · 익절 {r.take_profit_pct?.toFixed(1)}%
                  {r.sl_tp_source ? ` (${r.sl_tp_source})` : ""}
                  {" · "}
                </>
              )}
              {r.price_usdt && r.price_usdt > 0 && (
                <>
                  ${fmtUsd(r.price_usdt)} · 익 +{fmtKrw(r.take_profit_krw ?? 0)} / 손 -
                  {fmtKrw(r.stop_loss_krw ?? 0)}원
                </>
              )}
            </p>
          </li>
        ))}
      </ul>

      <p className="alerts-foot-meta">
        합계 {fmtKrw(total)}원 · 배분 가능 {fmtKrw(deployable)}원
        {total > deployable && (
          <span className="warn"> — 차트에서 금액 조절 필요</span>
        )}
      </p>
    </div>
  );
}

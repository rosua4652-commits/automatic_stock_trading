import type { AppConfig } from "../types";
import type { ApplyItem, EditableRecommendation } from "../hooks/useRecommendationAmounts";
import { fmtKrw, fmtPctSetting, fmtUsd } from "../utils";
import RecommendationAmountField from "./RecommendationAmountField";

type Props = {
  list: EditableRecommendation[];
  aiAmounts: Record<string, number>;
  config: AppConfig;
  cashKrw: number;
  busy: boolean;
  onAmountChange: (symbol: string, amount: number) => void;
  onResetAi: (symbol: string) => void;
  onApply: (items: ApplyItem[]) => Promise<void>;
  onSelect: (symbol: string) => void;
};

export default function EntryOpportunitiesPanel({
  list,
  aiAmounts,
  config,
  cashKrw,
  busy,
  onAmountChange,
  onResetAi,
  onApply,
  onSelect,
}: Props) {
  const actionable = list.filter(
    (r) => r.entry_tier === "auto" || r.entry_tier === "scalp"
  );
  const rows = actionable.length > 0 ? actionable : list;

  if (rows.length === 0) {
    return (
      <section className="panel-block entry-opp-panel empty">
        <h3>진입 가능 코인</h3>
        <p className="empty">분석 후 조건 충족 시 여기에 제안·익절/손절 예상이 표시됩니다</p>
      </section>
    );
  }

  const total = rows.reduce((s, r) => s + r.amount_krw, 0);

  const applyRows = (symbols: string[]) => {
    onApply(
      symbols.map((sym) => {
        const row = rows.find((r) => r.symbol === sym);
        return { symbol: sym, amount_krw: row?.amount_krw ?? 0 };
      })
    );
  };

  return (
    <section className="panel-block entry-opp-panel">
      <div className="entry-opp-head">
        <h3>진입 가능 · 승인 매수</h3>
        <span className="entry-opp-meta">
          {rows.length}종 · 합계 {fmtKrw(total)}원
        </span>
      </div>
      <p className="panel-hint">
        AI 제안 금액을 수정할 수 있습니다 · 승인 시 익절{" "}
        {fmtPctSetting(config.take_profit_pct)} / 손절{" "}
        {fmtPctSetting(config.stop_loss_pct)} 자동 매도
      </p>
      <ul className="entry-opp-list">
        {rows.map((r) => (
          <li key={r.symbol} className="entry-opp-item">
            <button
              type="button"
              className="entry-opp-coin"
              onClick={() => onSelect(r.symbol)}
            >
              <div className="entry-opp-coin-names">
                <span className="entry-opp-ko">{r.name_ko}</span>
                <span className="entry-opp-base">{r.base}</span>
              </div>
              <span
                className={`entry-opp-tier ${r.entry_tier === "auto" ? "auto" : "scalp"}`}
              >
                {r.entry_tier === "auto" ? "진입 가능" : "단타 가능"}
              </span>
            </button>

            <RecommendationAmountField
              row={r}
              aiAmount={aiAmounts[r.symbol] ?? r.amount_krw}
              cashKrw={cashKrw}
              disabled={busy}
              onAmountChange={onAmountChange}
              onResetAi={onResetAi}
            />

            <div className="entry-opp-plan">
              {r.price_usdt && r.price_usdt > 0 && (
                <div className="entry-opp-row dim">
                  <span>예상 매수</span>
                  <span>
                    ${fmtUsd(r.price_usdt)} · 약 {(r.quantity_est ?? 0).toFixed(4)}개
                  </span>
                </div>
              )}
              <div className="entry-opp-row up">
                <span>익절 예상</span>
                <span>
                  +{fmtKrw(r.take_profit_krw ?? 0)}원
                  {r.take_profit_price_usdt
                    ? ` ($${fmtUsd(r.take_profit_price_usdt)})`
                    : ""}
                </span>
              </div>
              <div className="entry-opp-row down">
                <span>손절 예상</span>
                <span>
                  -{fmtKrw(r.stop_loss_krw ?? 0)}원
                  {r.stop_loss_price_usdt
                    ? ` ($${fmtUsd(r.stop_loss_price_usdt)})`
                    : ""}
                </span>
              </div>
            </div>
            <button
              type="button"
              className="btn-primary btn-sm entry-opp-approve"
              disabled={busy || r.amount_krw > cashKrw || r.amount_krw < 5000}
              onClick={() => applyRows([r.symbol])}
            >
              승인 매수
            </button>
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="btn-primary entry-opp-approve-all"
        disabled={busy || total > cashKrw}
        onClick={() => applyRows(rows.map((r) => r.symbol))}
      >
        {busy ? "처리 중…" : `전체 승인 (${rows.length}건 · ${fmtKrw(total)}원)`}
      </button>
      {total > cashKrw && (
        <p className="warn">현금 부족 — 금액을 줄이거나 일부만 승인하세요</p>
      )}
    </section>
  );
}

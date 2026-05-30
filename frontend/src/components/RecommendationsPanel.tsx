import { useEffect, useState } from "react";
import type { EditableRecommendation } from "../hooks/useRecommendationAmounts";
import type { ApplyItem } from "../hooks/useRecommendationAmounts";
import { deployableCashKrw, fmtKrw, fmtPct, fmtUsd, isRunning } from "../utils";
import RecommendationAmountField from "./RecommendationAmountField";

type Props = {
  list: EditableRecommendation[];
  aiAmounts: Record<string, number>;
  botStatus: string;
  cashKrw: number;
  busy: boolean;
  onAmountChange: (symbol: string, amount: number) => void;
  onResetAi: (symbol: string) => void;
  onApply: (items: ApplyItem[]) => Promise<void>;
  variant?: "full" | "sidebar";
};

export default function RecommendationsPanel({
  list,
  aiAmounts,
  botStatus,
  cashKrw,
  busy,
  onAmountChange,
  onResetAi,
  onApply,
  variant = "full",
}: Props) {
  const sidebar = variant === "sidebar";
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    const m: Record<string, boolean> = {};
    list.forEach((r) => {
      m[r.symbol] = selected[r.symbol] ?? r.selected !== false;
    });
    setSelected(m);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list]);

  const running = isRunning(botStatus);
  const picked = list.filter((r) => selected[r.symbol] !== false);
  const total = picked.reduce((s, r) => s + r.amount_krw, 0);
  const deployable = deployableCashKrw(cashKrw);
  const overBudget = total > deployable + 500;

  const toggle = (sym: string) => {
    setSelected((prev) => ({ ...prev, [sym]: !prev[sym] }));
  };

  const toggleAll = (on: boolean) => {
    const m: Record<string, boolean> = {};
    list.forEach((r) => {
      m[r.symbol] = on;
    });
    setSelected(m);
  };

  const applyPicked = () => {
    onApply(
      picked.map((r) => ({ symbol: r.symbol, amount_krw: r.amount_krw }))
    );
  };

  if (list.length === 0) {
    return (
      <section className={`rec-panel empty ${sidebar ? "rec-sidebar" : ""}`}>
        <h3>투자 제안</h3>
        <p className="empty">
          {running
            ? "분석 중…"
            : "분석 시작 → AI 제안 (금액 조절 후 승인 · 익절/손절 자동)"}
        </p>
      </section>
    );
  }

  return (
    <section className={`rec-panel ${sidebar ? "rec-sidebar" : ""}`}>
      <div className="rec-head">
        <h3>투자 제안</h3>
        <p className="panel-hint">AI 금액 수정 가능 · 승인 시 손절/익절 자동</p>
        <span className="rec-meta">
          현금 {fmtKrw(cashKrw)}원 · 배분 가능 {fmtKrw(deployable)}원 · 선택{" "}
          {picked.length}건 · 합계 {fmtKrw(total)}원
          {overBudget && (
            <span className="warn"> (현금 초과 — 자동 조절됨)</span>
          )}
        </span>
      </div>
      <div className="rec-actions-top">
        <button type="button" className="btn-ghost btn-sm" onClick={() => toggleAll(true)}>
          전체 선택
        </button>
        <button type="button" className="btn-ghost btn-sm" onClick={() => toggleAll(false)}>
          전체 해제
        </button>
        <button
          type="button"
          className="btn-primary"
          disabled={busy || picked.length === 0 || total > deployable + 500}
          onClick={applyPicked}
        >
          {busy ? "매수 중…" : `선택 승인 (${picked.length}건)`}
        </button>
      </div>
      {total > cashKrw && (
        <p className="warn">선택 금액이 현금보다 큽니다.</p>
      )}
      <div className="rec-table-wrap">
        {sidebar ? (
          <ul className="rec-list-compact">
            {list.map((r) => (
              <li key={r.symbol} className={selected[r.symbol] ? "" : "dim"}>
                <label className="rec-row-compact">
                  <input
                    type="checkbox"
                    checked={selected[r.symbol] !== false}
                    onChange={() => toggle(r.symbol)}
                  />
                  <span className="rec-row-name">{r.name_ko}</span>
                  <button
                    type="button"
                    className="rec-row-amt-btn"
                    onClick={(e) => {
                      e.preventDefault();
                      setExpanded(expanded === r.symbol ? null : r.symbol);
                    }}
                  >
                    {fmtKrw(r.amount_krw)}원
                  </button>
                </label>
                {expanded === r.symbol && (
                  <div className="rec-expand">
                    <RecommendationAmountField
                      row={r}
                      aiAmount={aiAmounts[r.symbol] ?? r.amount_krw}
                      cashKrw={cashKrw}
                      disabled={busy}
                      onAmountChange={onAmountChange}
                      onResetAi={onResetAi}
                    />
                  </div>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <table className="rec-table">
            <thead>
              <tr>
                <th />
                <th>코인</th>
                <th>매수 금액</th>
                <th>익절/손절</th>
                <th>24h</th>
              </tr>
            </thead>
            <tbody>
              {list.map((r) => (
                <tr key={r.symbol} className={selected[r.symbol] ? "" : "dim"}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selected[r.symbol] !== false}
                      onChange={() => toggle(r.symbol)}
                    />
                  </td>
                  <td>
                    <strong>{r.name_ko}</strong>
                    <span className="dim">{r.base}</span>
                  </td>
                  <td className="amount">
                    <input
                      type="number"
                      className="rec-amount-input compact"
                      min={5000}
                      step={1000}
                      value={r.amount_krw}
                      disabled={busy}
                      onChange={(e) =>
                        onAmountChange(r.symbol, Number(e.target.value) || 5000)
                      }
                    />
                    <span className="dim"> AI {fmtKrw(aiAmounts[r.symbol] ?? 0)}</span>
                  </td>
                  <td className="rec-qty">
                    <span className="up">+{fmtKrw(r.take_profit_krw ?? 0)}</span>
                    <br />
                    <span className="down">-{fmtKrw(r.stop_loss_krw ?? 0)}</span>
                  </td>
                  <td className={r.change_24h >= 0 ? "up" : "down"}>
                    {fmtPct(r.change_24h)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

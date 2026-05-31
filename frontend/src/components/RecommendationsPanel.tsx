import { useEffect, useState } from "react";
import type { EditableRecommendation } from "../hooks/useRecommendationAmounts";
import type { ApplyItem } from "../hooks/useRecommendationAmounts";
import { deployableCashKrw, fmtKrw, fmtPct, fmtUsd, isRunning } from "../utils";
import CollapsibleSection from "./CollapsibleSection";
import RecommendationAmountField from "./RecommendationAmountField";

const REC_PANEL_STORAGE = "aidi-rec-panel-collapsed";

type Props = {
  list: EditableRecommendation[];
  aiAmounts: Record<string, number>;
  botStatus: string;
  cashKrw: number;
  feePct?: number;
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
  feePct = 0.05,
  busy,
  onAmountChange,
  onResetAi,
  onApply,
  variant = "full",
}: Props) {
  const sidebar = variant === "sidebar";
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [amountRowOpen, setAmountRowOpen] = useState<string | null>(null);

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
  const deployable = deployableCashKrw(cashKrw, feePct);
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

  const panelClass = `rec-panel ${sidebar ? "rec-sidebar" : ""}${
    list.length === 0 ? " empty" : ""
  }`;

  const body =
    list.length === 0 ? (
      <p className="empty">
        {running
          ? "분석 중…"
          : "분석 시작 → AI 제안 (금액 조절 후 승인 · 익절/손절 자동)"}
      </p>
    ) : (
      <>
      <div className="rec-head">
        <p className="panel-hint">
          AI 금액 수정 가능 · 승인 시 손절/익절 자동 · 수수료 편도 {feePct}% (왕복{" "}
          {(feePct * 2).toFixed(2)}% 반영)
        </p>
        <span className="rec-meta">
          현금 {fmtKrw(cashKrw)}원 · 배분 가능 {fmtKrw(deployable)}원 · 선택{" "}
          {picked.length}건 · 합계 {fmtKrw(total)}원
          {overBudget && (
            <span className="warn"> (현금 초과 — 자동 조절됨)</span>
          )}
        </span>
      </div>
      <div className="rec-actions-top">
        <button
          type="button"
          className="rec-chip-btn"
          onClick={() => toggleAll(true)}
        >
          전체선택
        </button>
        <button
          type="button"
          className="rec-chip-btn"
          onClick={() => toggleAll(false)}
        >
          전체해제
        </button>
        <button
          type="button"
          className="btn-primary rec-apply-btn"
          disabled={busy || picked.length === 0 || total > deployable + 500}
          onClick={applyPicked}
        >
          {busy ? "매수 중…" : `승인(${picked.length})`}
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
                      setAmountRowOpen(
                        amountRowOpen === r.symbol ? null : r.symbol
                      );
                    }}
                  >
                    {fmtKrw(r.amount_krw)}원
                  </button>
                </label>
                {amountRowOpen === r.symbol && (
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
                <th>BT 손익절</th>
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
                    {(r.stop_loss_pct ?? 0) > 0 ? (
                      <>
                        <span className="rec-sltp-pct">
                          손절 {fmtPct(r.stop_loss_pct ?? 0)} · 익절{" "}
                          {fmtPct(r.take_profit_pct ?? 0)}
                        </span>
                        {r.sl_tp_source ? (
                          <span className="dim"> ({r.sl_tp_source})</span>
                        ) : null}
                        <br />
                        <span className="up">+{fmtKrw(r.take_profit_krw ?? 0)}</span>
                        <span className="dim"> / </span>
                        <span className="down">-{fmtKrw(r.stop_loss_krw ?? 0)}</span>
                      </>
                    ) : (
                      <>
                        <span className="up">+{fmtKrw(r.take_profit_krw ?? 0)}</span>
                        <br />
                        <span className="down">-{fmtKrw(r.stop_loss_krw ?? 0)}</span>
                      </>
                    )}
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
      </>
    );

  const collapsedHint =
    list.length === 0 && running
      ? "분석 중… · 파란 「펼치기」를 누르면 안내 표시"
      : list.length > 0
        ? `${list.length}건 · 「펼치기」로 목록 보기`
        : undefined;

  return (
    <CollapsibleSection
      title="투자 제안"
      storageKey={REC_PANEL_STORAGE}
      defaultCollapsed={list.length === 0}
      count={list.length}
      collapsedHint={collapsedHint}
      className={panelClass}
    >
      {body}
    </CollapsibleSection>
  );
}

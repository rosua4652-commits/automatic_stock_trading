import { useEffect } from "react";
import type { AppConfig } from "../types";
import type { ApplyItem, EditableRecommendation } from "../hooks/useRecommendationAmounts";
import { fmtKrw, fmtUsd } from "../utils";
import RecommendationAmountField from "./RecommendationAmountField";

type Props = {
  open: boolean;
  list: EditableRecommendation[];
  aiAmounts: Record<string, number>;
  config: AppConfig;
  cashKrw: number;
  busy: boolean;
  onAmountChange: (symbol: string, amount: number) => void;
  onResetAi: (symbol: string) => void;
  onClose: () => void;
  onApply: (items: ApplyItem[]) => Promise<void>;
  onSelect: (symbol: string) => void;
};

export default function EntryAlertModal({
  open,
  list,
  aiAmounts,
  config,
  cashKrw,
  busy,
  onAmountChange,
  onResetAi,
  onClose,
  onApply,
  onSelect,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || list.length === 0) return null;

  const total = list.reduce((s, r) => s + r.amount_krw, 0);
  const top = list.slice(0, 4);

  return (
    <div className="entry-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="entry-modal"
        role="dialog"
        aria-labelledby="entry-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="entry-modal-head">
          <h2 id="entry-modal-title">진입 가능 코인 발견</h2>
          <button type="button" className="btn-ghost btn-sm" onClick={onClose}>
            닫기
          </button>
        </header>
        <p className="entry-modal-sub">
          금액 조절 후 승인 · 익절 {config.take_profit_pct}% / 손절{" "}
          {config.stop_loss_pct}% 자동 매도
        </p>
        <ul className="entry-modal-list">
          {top.map((r) => (
            <li key={r.symbol} className="entry-modal-item">
              <button
                type="button"
                className="entry-modal-row"
                onClick={() => {
                  onSelect(r.symbol);
                  onClose();
                }}
              >
                <div>
                  <strong>{r.name_ko}</strong>
                  <span className="dim"> {r.base}</span>
                </div>
              </button>
              <RecommendationAmountField
                row={r}
                aiAmount={aiAmounts[r.symbol] ?? r.amount_krw}
                cashKrw={cashKrw}
                disabled={busy}
                onAmountChange={onAmountChange}
                onResetAi={onResetAi}
              />
              <p className="entry-modal-detail">
                {(r.quantity_est ?? 0) > 0 && r.price_usdt
                  ? `≈ ${(r.quantity_est ?? 0).toFixed(4)}개 @ $${fmtUsd(r.price_usdt)} · `
                  : ""}
                익절 +{fmtKrw(r.take_profit_krw ?? 0)} / 손절 -
                {fmtKrw(r.stop_loss_krw ?? 0)}원
              </p>
            </li>
          ))}
        </ul>
        {list.length > 4 && (
          <p className="dim entry-modal-more">
            외 {list.length - 4}종 — 왼쪽 패널에서 금액 조절
          </p>
        )}
        <div className="entry-modal-actions">
          <button
            type="button"
            className="btn-primary"
            disabled={busy || total > cashKrw}
            onClick={() => {
              onApply(list.map((r) => ({ symbol: r.symbol, amount_krw: r.amount_krw })));
              onClose();
            }}
          >
            전체 승인 ({fmtKrw(total)}원)
          </button>
          <button type="button" className="btn-ghost" onClick={onClose}>
            나중에
          </button>
        </div>
      </div>
    </div>
  );
}

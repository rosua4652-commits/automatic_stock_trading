import { useEffect } from "react";
import type { AppConfig, InvestmentRecommendation } from "../types";
import { fmtKrw, fmtUsd } from "../utils";

type Props = {
  open: boolean;
  recommendations: InvestmentRecommendation[];
  config: AppConfig;
  cashKrw: number;
  busy: boolean;
  onClose: () => void;
  onApply: (symbols: string[]) => Promise<void>;
  onSelect: (symbol: string) => void;
};

export default function EntryAlertModal({
  open,
  recommendations,
  config,
  cashKrw,
  busy,
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

  if (!open || recommendations.length === 0) return null;

  const total = recommendations.reduce((s, r) => s + r.amount_krw, 0);
  const top = recommendations.slice(0, 6);

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
          {recommendations.length}종 · 합계 {fmtKrw(total)}원 · 익절{" "}
          {config.take_profit_pct}% / 손절 {config.stop_loss_pct}%
        </p>
        <ul className="entry-modal-list">
          {top.map((r) => (
            <li key={r.symbol}>
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
                <span>{fmtKrw(r.amount_krw)}원</span>
              </button>
              <p className="entry-modal-detail">
                {(r.quantity_est ?? 0) > 0 && r.price_usdt
                  ? `≈ ${(r.quantity_est ?? 0).toFixed(4)}개 @ $${fmtUsd(r.price_usdt)} · `
                  : ""}
                익절 +{fmtKrw(r.take_profit_krw ?? 0)}원 / 손절 -
                {fmtKrw(r.stop_loss_krw ?? 0)}원
              </p>
            </li>
          ))}
        </ul>
        {recommendations.length > 6 && (
          <p className="dim entry-modal-more">
            외 {recommendations.length - 6}종 — 왼쪽 「진입 가능」 패널에서 확인
          </p>
        )}
        <div className="entry-modal-actions">
          <button
            type="button"
            className="btn-primary"
            disabled={busy || total > cashKrw}
            onClick={() => {
              onApply(recommendations.map((r) => r.symbol));
              onClose();
            }}
          >
            전체 승인 매수
          </button>
          <button type="button" className="btn-ghost" onClick={onClose}>
            나중에
          </button>
        </div>
      </div>
    </div>
  );
}

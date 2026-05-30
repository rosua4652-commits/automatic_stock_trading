import { useEffect, useState } from "react";
import type { ApplyItem, EditableRecommendation } from "../hooks/useRecommendationAmounts";
import { fmtKrw, fmtUsd } from "../utils";

type Props = {
  list: EditableRecommendation[];
  cashKrw: number;
  busy: boolean;
  onApply: (items: ApplyItem[]) => Promise<void>;
  onSelectSymbol?: (symbol: string) => void;
};

export default function RecommendationAlert({
  list,
  cashKrw,
  busy,
  onApply,
  onSelectSymbol,
}: Props) {
  const [open, setOpen] = useState(true);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (list.length > 0) {
      setDismissed(false);
      setOpen(true);
    }
  }, [list]);

  if (list.length === 0 || dismissed) {
    return null;
  }

  const total = list.reduce((s, r) => s + r.amount_krw, 0);
  const top = list.slice(0, 5);

  return (
    <div className={`rec-alert ${open ? "open" : "collapsed"}`} role="dialog" aria-label="투자 제안 알림">
      <div className="rec-alert-head">
        <strong>진입 가능 {list.length}종</strong>
        <span className="rec-alert-sum">합계 {fmtKrw(total)}원</span>
        <div className="rec-alert-head-btns">
          <button
            type="button"
            className="btn-ghost btn-sm"
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "접기" : "펼치기"}
          </button>
          <button
            type="button"
            className="btn-ghost btn-sm"
            onClick={() => setDismissed(true)}
            aria-label="닫기"
          >
            ✕
          </button>
        </div>
      </div>
      {open && (
        <>
          <p className="panel-hint rec-alert-hint">승인 시 익절·손절 자동 (왼쪽에서 금액 조절)</p>
          <ul className="rec-alert-list">
            {top.map((r) => (
              <li key={r.symbol}>
                <button
                  type="button"
                  className="rec-alert-row"
                  onClick={() => onSelectSymbol?.(r.symbol)}
                >
                  <span className="rec-alert-name">{r.name_ko}</span>
                  <span className="rec-alert-amt">{fmtKrw(r.amount_krw)}원</span>
                </button>
                <span className="rec-alert-detail">
                  {r.price_usdt && r.price_usdt > 0 && (
                    <>
                      ${fmtUsd(r.price_usdt)} · 약 {(r.quantity_est ?? 0).toFixed(4)}개 ·{" "}
                    </>
                  )}
                  익절 +{fmtKrw(r.take_profit_krw ?? 0)} / 손절 -
                  {fmtKrw(r.stop_loss_krw ?? 0)}원
                </span>
              </li>
            ))}
          </ul>
          {list.length > 5 && (
            <p className="rec-alert-more">외 {list.length - 5}종 · 왼쪽 패널에서 금액 조절</p>
          )}
          <div className="rec-alert-actions">
            <button
              type="button"
              className="btn-primary btn-sm"
              disabled={busy || total > cashKrw}
              onClick={() =>
                onApply(list.map((r) => ({ symbol: r.symbol, amount_krw: r.amount_krw })))
              }
            >
              {busy ? "매수 중…" : `전체 승인 (${list.length}건)`}
            </button>
          </div>
          {total > cashKrw && (
            <p className="warn">현금 {fmtKrw(cashKrw)}원 — 금액 조절 필요</p>
          )}
        </>
      )}
    </div>
  );
}

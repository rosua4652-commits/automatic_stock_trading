import { useEffect, useState } from "react";
import type { InvestmentRecommendation } from "../types";
import { fmtKrw, fmtPct, isRunning } from "../utils";

type Props = {
  recommendations: InvestmentRecommendation[];
  botStatus: string;
  cashKrw: number;
  busy: boolean;
  onApply: (symbols: string[]) => Promise<void>;
};

export default function RecommendationsPanel({
  recommendations,
  botStatus,
  cashKrw,
  busy,
  onApply,
}: Props) {
  const [selected, setSelected] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const m: Record<string, boolean> = {};
    recommendations.forEach((r) => {
      m[r.symbol] = selected[r.symbol] ?? r.selected !== false;
    });
    setSelected(m);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recommendations]);

  const running = isRunning(botStatus);
  const list = recommendations;
  const picked = list.filter((r) => selected[r.symbol] !== false);
  const total = picked.reduce((s, r) => s + r.amount_krw, 0);

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

  if (list.length === 0) {
    return (
      <section className="rec-panel empty">
        <h3>AI 투자 제안</h3>
        <p className="empty">
          {running
            ? "시장 분석 중… 잠시 후 제안 목록이 채워집니다."
            : "「분석 시작」을 누르면 시장에서 코인을 골라 비중·금액을 제안합니다."}
        </p>
      </section>
    );
  }

  return (
    <section className="rec-panel">
      <div className="rec-head">
        <h3>AI 투자 제안</h3>
        <span className="rec-meta">
          현금 {fmtKrw(cashKrw)}원 · 선택 {picked.length}건 · 합계 {fmtKrw(total)}원
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
          disabled={busy || picked.length === 0 || total > cashKrw}
          onClick={() => onApply(picked.map((r) => r.symbol))}
        >
          {busy ? "매수 중…" : `선택 승인 매수 (${picked.length}건)`}
        </button>
      </div>
      {total > cashKrw && (
        <p className="warn">선택 금액이 현금보다 큽니다. 일부만 선택하세요.</p>
      )}
      <div className="rec-table-wrap">
        <table className="rec-table">
          <thead>
            <tr>
              <th />
              <th>코인</th>
              <th>시장</th>
              <th>차트</th>
              <th>비중</th>
              <th>제안 금액</th>
              <th>24h</th>
              <th>근거</th>
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
                  <span className="dim">{r.pair_label}</span>
                </td>
                <td>{r.market_score}</td>
                <td>{r.entry_score}</td>
                <td>{r.weight_pct}%</td>
                <td className="amount">{fmtKrw(r.amount_krw)}원</td>
                <td className={r.change_24h >= 0 ? "up" : "down"}>{fmtPct(r.change_24h)}</td>
                <td className="rec-reason">{r.entry_detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

import { useEffect, useState } from "react";
import type { InvestmentRecommendation } from "../types";
import { fmtKrw, fmtPct, isRunning } from "../utils";

type Props = {
  recommendations: InvestmentRecommendation[];
  botStatus: string;
  cashKrw: number;
  busy: boolean;
  onApply: (symbols: string[]) => Promise<void>;
  variant?: "full" | "sidebar";
};

export default function RecommendationsPanel({
  recommendations,
  botStatus,
  cashKrw,
  busy,
  onApply,
  variant = "full",
}: Props) {
  const sidebar = variant === "sidebar";
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
      <section className={`rec-panel empty ${sidebar ? "rec-sidebar" : ""}`}>
        <h3>투자 제안</h3>
        <p className="empty">
          {running
            ? "분석 중…"
            : "분석 시작 → 조건 충족 코인만 제안 (단타는 분석 목록에서 직접 매수 가능)"}
        </p>
      </section>
    );
  }

  return (
    <section className={`rec-panel ${sidebar ? "rec-sidebar" : ""}`}>
      <div className="rec-head">
        <h3>투자 제안</h3>
        <p className="panel-hint">자동 추천·단타 가능 코인만 금액 제안 (전체 탭과 다름)</p>
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
                  <span className="rec-row-amt">{fmtKrw(r.amount_krw)}</span>
                  <span className="rec-row-pct">{r.weight_pct}%</span>
                </label>
              </li>
            ))}
          </ul>
        ) : (
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
                  <td className={r.change_24h >= 0 ? "up" : "down"}>
                    {fmtPct(r.change_24h)}
                  </td>
                  <td className="rec-reason">{r.entry_detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

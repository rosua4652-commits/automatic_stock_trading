import type { AppConfig, InvestmentRecommendation } from "../types";
import { fmtKrw, fmtUsd } from "../utils";

type Props = {
  recommendations: InvestmentRecommendation[];
  config: AppConfig;
  cashKrw: number;
  busy: boolean;
  onApply: (symbols: string[]) => Promise<void>;
  onSelect: (symbol: string) => void;
};

export default function EntryOpportunitiesPanel({
  recommendations,
  config,
  cashKrw,
  busy,
  onApply,
  onSelect,
}: Props) {
  const actionable = recommendations.filter(
    (r) => r.entry_tier === "auto" || r.entry_tier === "scalp"
  );
  const list = actionable.length > 0 ? actionable : recommendations;

  if (list.length === 0) {
    return (
      <section className="panel-block entry-opp-panel empty">
        <h3>진입 가능 코인</h3>
        <p className="empty">분석 후 조건 충족 시 여기에 제안·익절/손절 예상이 표시됩니다</p>
      </section>
    );
  }

  const total = list.reduce((s, r) => s + r.amount_krw, 0);

  return (
    <section className="panel-block entry-opp-panel">
      <div className="entry-opp-head">
        <h3>진입 가능 · 승인 매수</h3>
        <span className="entry-opp-meta">
          {list.length}종 · 합계 {fmtKrw(total)}원
        </span>
      </div>
      <p className="panel-hint">
        익절 {config.take_profit_pct}% · 손절 {config.stop_loss_pct}% (설정 기준 예상)
      </p>
      <ul className="entry-opp-list">
        {list.map((r) => (
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
            <div className="entry-opp-plan">
              <div className="entry-opp-row">
                <span>매수</span>
                <strong>{fmtKrw(r.amount_krw)}원</strong>
              </div>
              {r.price_usdt && r.price_usdt > 0 && (
                <div className="entry-opp-row dim">
                  <span>가격·수량</span>
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
              disabled={busy || r.amount_krw > cashKrw}
              onClick={() => onApply([r.symbol])}
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
        onClick={() => onApply(list.map((r) => r.symbol))}
      >
        {busy ? "처리 중…" : `전체 승인 (${list.length}건 · ${fmtKrw(total)}원)`}
      </button>
      {total > cashKrw && (
        <p className="warn">현금 부족 — 일부만 승인하세요</p>
      )}
    </section>
  );
}

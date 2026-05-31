import type { EditableRecommendation } from "../hooks/useRecommendationAmounts";
import { fmtKrw } from "../utils";

type Props = {
  row: EditableRecommendation;
  aiAmount: number;
  cashKrw: number;
  minBuyKrw?: number;
  disabled?: boolean;
  onAmountChange: (symbol: string, amount: number) => void;
  onResetAi: (symbol: string) => void;
};

export default function RecommendationAmountField({
  row,
  aiAmount,
  cashKrw,
  minBuyKrw = 10_000,
  disabled,
  onAmountChange,
  onResetAi,
}: Props) {
  const minBuy = Math.max(5_000, Math.round(minBuyKrw / 1000) * 1000);
  const changed = row.amount_krw !== aiAmount;

  return (
    <div className="rec-amount-field">
      <div className="rec-amount-row">
        <label className="rec-amount-label">
          매수 금액
          <span className="dim"> (AI {fmtKrw(aiAmount)}원)</span>
        </label>
        <div className="rec-amount-input-wrap">
          <input
            type="number"
            className="rec-amount-input"
            min={minBuy}
            step={1000}
            value={row.amount_krw}
            disabled={disabled}
            onChange={(e) =>
              onAmountChange(row.symbol, Number(e.target.value) || minBuy)
            }
          />
          <span className="rec-amount-unit">원</span>
          {changed && (
            <button
              type="button"
              className="btn-ghost btn-sm"
              disabled={disabled}
              onClick={() => onResetAi(row.symbol)}
            >
              AI
            </button>
          )}
        </div>
      </div>
      {row.amount_krw > cashKrw && (
        <p className="trade-hint warn">현금 초과</p>
      )}
      <p className="rec-amount-hint auto-tag">
        승인 시 익절·손절 자동 매도 (AI 관리)
      </p>
    </div>
  );
}

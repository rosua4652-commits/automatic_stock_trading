import { useEffect, useMemo } from "react";
import { fmtKrw, MIN_BUY_KRW } from "../utils";

const MIN_KRW = MIN_BUY_KRW;
const STEP = 1_000;

const PRESETS: { label: string; ratio: number }[] = [
  { label: "5%", ratio: 0.05 },
  { label: "10%", ratio: 0.1 },
  { label: "25%", ratio: 0.25 },
  { label: "50%", ratio: 0.5 },
  { label: "75%", ratio: 0.75 },
  { label: "전액", ratio: 1 },
];

type Props = {
  cashKrw: number;
  value: number;
  onChange: (amount: number) => void;
  disabled?: boolean;
  id?: string;
};

function clampAmount(amount: number, maxKrw: number) {
  const max = Math.max(MIN_KRW, maxKrw);
  const n = Math.round(amount / STEP) * STEP;
  return Math.min(max, Math.max(MIN_KRW, n));
}

export function maxBuyKrw(cashKrw: number) {
  return Math.max(MIN_KRW, Math.floor(cashKrw * 0.95));
}

export default function BuyAmountControl({
  cashKrw,
  value,
  onChange,
  disabled,
  id = "buy-amount",
}: Props) {
  const maxKrw = useMemo(() => maxBuyKrw(cashKrw), [cashKrw]);

  const pct = useMemo(() => {
    if (cashKrw <= 0) return 0;
    return Math.min(100, Math.round((value / cashKrw) * 100));
  }, [value, cashKrw]);

  useEffect(() => {
    const clamped = clampAmount(value, maxKrw);
    if (clamped !== value) onChange(clamped);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [maxKrw]);

  const setPreset = (ratio: number) => {
    onChange(clampAmount(cashKrw * ratio, maxKrw));
  };

  const insufficient = value > cashKrw;
  const activePreset = PRESETS.find(
    (p) => Math.abs(clampAmount(cashKrw * p.ratio, maxKrw) - value) < STEP
  )?.label;

  return (
    <div className={`buy-amount-control buy-amount-stack ${disabled ? "disabled" : ""}`}>
      <div className="buy-amount-head">
        <span className="buy-amount-label">매수 금액</span>
        <span className="buy-amount-cash">
          보유 <strong>{fmtKrw(cashKrw)}</strong>원
          <span className="dim"> · 매수 가능 최대 {fmtKrw(maxKrw)}원</span>
        </span>
      </div>

      <div className="buy-amount-input-row">
        <input
          id={id}
          type="number"
          className="buy-amount-number"
          min={MIN_KRW}
          max={maxKrw}
          step={STEP}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(clampAmount(Number(e.target.value), maxKrw))}
        />
        <span className="buy-amount-unit">원</span>
      </div>

      <p className="buy-amount-summary">
        선택 <strong>{fmtKrw(value)}</strong>원
        {cashKrw > 0 && (
          <span className="dim"> · 현금의 {pct}%</span>
        )}
      </p>

      <div className="buy-amount-presets buy-amount-presets-stack" role="group" aria-label="비율 선택">
        {PRESETS.map((p) => {
          const amt = clampAmount(cashKrw * p.ratio, maxKrw);
          const active = activePreset === p.label;
          return (
            <button
              key={p.label}
              type="button"
              className={`preset-btn preset-btn-stack ${active ? "active" : ""}`}
              disabled={disabled || cashKrw < MIN_KRW}
              onClick={() => setPreset(p.ratio)}
            >
              <span className="preset-label">{p.label}</span>
              <span className="preset-amt">{fmtKrw(amt)}원</span>
            </button>
          );
        })}
      </div>

      {insufficient && (
        <p className="trade-hint warn">입력 금액이 현금보다 큽니다.</p>
      )}
      {cashKrw < MIN_KRW && (
        <p className="trade-hint warn">최소 매수 금액은 {fmtKrw(MIN_KRW)}원입니다.</p>
      )}
    </div>
  );
}

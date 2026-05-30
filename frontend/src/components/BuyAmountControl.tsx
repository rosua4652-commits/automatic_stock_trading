import { useEffect, useMemo } from "react";
import { fmtKrw } from "../utils";

const MIN_KRW = 50_000;
const STEP = 10_000;

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
    if (maxKrw <= MIN_KRW) return 100;
    return Math.round(((value - MIN_KRW) / (maxKrw - MIN_KRW)) * 100);
  }, [value, maxKrw]);

  useEffect(() => {
    const clamped = clampAmount(value, maxKrw);
    if (clamped !== value) onChange(clamped);
    // maxKrw 변경 시에만 보정 (무한 루프 방지)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [maxKrw]);

  const setFromPct = (p: number) => {
    const ratio = Math.min(100, Math.max(0, p)) / 100;
    const raw = MIN_KRW + (maxKrw - MIN_KRW) * ratio;
    onChange(clampAmount(raw, maxKrw));
  };

  const setPreset = (ratio: number) => {
    onChange(clampAmount(cashKrw * ratio, maxKrw));
  };

  const insufficient = value > cashKrw;

  return (
    <div className={`buy-amount-control ${disabled ? "disabled" : ""}`}>
      <div className="buy-amount-head">
        <span className="buy-amount-label">매수 금액</span>
        <span className="buy-amount-cash">
          보유 현금 <strong>{fmtKrw(cashKrw)}</strong>원
          <span className="dim"> · 최대 {fmtKrw(maxKrw)}원</span>
        </span>
      </div>

      <div className="buy-amount-presets">
        {[0.1, 0.25, 0.5, 1].map((r) => (
          <button
            key={r}
            type="button"
            className="preset-btn"
            disabled={disabled || cashKrw < MIN_KRW}
            onClick={() => setPreset(r)}
          >
            {r === 1 ? "전액" : `${r * 100}%`}
          </button>
        ))}
      </div>

      <div className="buy-amount-slider-row">
        <input
          id={`${id}-range`}
          type="range"
          className="buy-amount-range"
          min={0}
          max={100}
          step={1}
          value={pct}
          disabled={disabled || maxKrw <= MIN_KRW}
          onChange={(e) => setFromPct(Number(e.target.value))}
        />
        <span className="buy-amount-pct">{pct}%</span>
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

      {insufficient && (
        <p className="trade-hint warn">입력 금액이 현금보다 큽니다.</p>
      )}
      {cashKrw < MIN_KRW && (
        <p className="trade-hint warn">최소 매수 금액은 {fmtKrw(MIN_KRW)}원입니다.</p>
      )}
    </div>
  );
}

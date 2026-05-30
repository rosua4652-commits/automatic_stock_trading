import { useEffect, useMemo } from "react";
import { fmtKrw, MIN_BUY_KRW } from "../utils";

const MIN_KRW = MIN_BUY_KRW;
const STEP = 1_000;

const PRESETS: { label: string; ratio: number }[] = [
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

  const sliderPct = useMemo(() => {
    if (maxKrw <= MIN_KRW) return 100;
    return Math.round(((value - MIN_KRW) / (maxKrw - MIN_KRW)) * 100);
  }, [value, maxKrw]);

  const cashPct = useMemo(() => {
    if (cashKrw <= 0) return 0;
    return Math.min(100, Math.round((value / cashKrw) * 100));
  }, [value, cashKrw]);

  useEffect(() => {
    const clamped = clampAmount(value, maxKrw);
    if (clamped !== value) onChange(clamped);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [maxKrw]);

  const setFromSlider = (p: number) => {
    const ratio = Math.min(100, Math.max(0, p)) / 100;
    const raw = MIN_KRW + (maxKrw - MIN_KRW) * ratio;
    onChange(clampAmount(raw, maxKrw));
  };

  const setPreset = (ratio: number) => {
    onChange(clampAmount(cashKrw * ratio, maxKrw));
  };

  const insufficient = value > cashKrw;

  return (
    <div className={`buy-amount-control buy-amount-compact ${disabled ? "disabled" : ""}`}>
      <div className="buy-amount-head">
        <span className="buy-amount-label">매수 금액</span>
        <span className="buy-amount-cash dim">
          보유 {fmtKrw(cashKrw)}원 · 최대 {fmtKrw(maxKrw)}원
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

      <div className="buy-amount-slider-row">
        <input
          type="range"
          className="buy-amount-range"
          min={0}
          max={100}
          step={1}
          value={sliderPct}
          disabled={disabled || maxKrw <= MIN_KRW}
          onChange={(e) => setFromSlider(Number(e.target.value))}
          aria-label="매수 금액 비율"
        />
        <span className="buy-amount-pct">{cashPct}%</span>
      </div>

      <div className="buy-amount-presets buy-amount-presets-inline" role="group" aria-label="비율 빠른 선택">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            type="button"
            className="preset-chip"
            disabled={disabled || cashKrw < MIN_KRW}
            onClick={() => setPreset(p.ratio)}
          >
            {p.label}
          </button>
        ))}
      </div>

      {insufficient && (
        <p className="trade-hint warn">현금보다 큽니다</p>
      )}
    </div>
  );
}

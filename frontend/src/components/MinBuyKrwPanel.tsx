import { useEffect, useState } from "react";
import { fmtKrw, UPBIT_MIN_ORDER_KRW } from "../utils";

type Props = {
  value: number;
  saving?: boolean;
  onSave: (minBuyKrw: number) => Promise<void>;
  compact?: boolean;
};

export default function MinBuyKrwPanel({
  value,
  saving,
  onSave,
  compact = false,
}: Props) {
  const [local, setLocal] = useState(value);

  useEffect(() => {
    setLocal(value);
  }, [value]);

  const apply = () => {
    const n = Math.max(
      UPBIT_MIN_ORDER_KRW,
      Math.round(Number(local) / 1000) * 1000
    );
    setLocal(n);
    void onSave(n);
  };

  return (
    <section
      className={`min-buy-panel panel-block ${compact ? "min-buy-panel-compact" : ""}`}
      aria-labelledby="min-buy-panel-title"
    >
      <div className="min-buy-panel-head">
        <h3 id="min-buy-panel-title">건당 최소 매수 금액</h3>
        <span className="min-buy-panel-current dim">
          적용 중 <strong>{fmtKrw(value)}원</strong>
        </span>
      </div>
      <p className="panel-hint">
        자동투자·승인 매수에만 적용. 수동 지정 매수는 업비트 하한{" "}
        {fmtKrw(UPBIT_MIN_ORDER_KRW)}원부터 가능.
      </p>
      <div className="min-buy-panel-row">
        <input
          type="number"
          className="min-buy-panel-input"
          min={UPBIT_MIN_ORDER_KRW}
          max={5_000_000}
          step={1000}
          value={local}
          disabled={saving}
          onChange={(e) => setLocal(Number(e.target.value) || UPBIT_MIN_ORDER_KRW)}
          onKeyDown={(e) => {
            if (e.key === "Enter") apply();
          }}
        />
        <span className="min-buy-panel-unit">원</span>
        <button
          type="button"
          className="btn-primary"
          disabled={saving || local < UPBIT_MIN_ORDER_KRW}
          onClick={apply}
        >
          {saving ? "저장 중…" : "저장"}
        </button>
      </div>
    </section>
  );
}

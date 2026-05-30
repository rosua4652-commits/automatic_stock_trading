import { fmtPctSetting, roundPct2 } from "../utils";

type Props = {
  stopLossPct: number;
  takeProfitPct: number;
  onStopLossChange: (pct: number) => void;
  onTakeProfitChange: (pct: number) => void;
  disabled?: boolean;
  /** 평단 대비 예상 가격 미리보기 (원) */
  previewSlKrw?: number;
  previewTpKrw?: number;
};

const SL_PRESETS = [1, 2, 3, 5, 8, 10];
const TP_PRESETS = [3, 5, 8, 10, 15, 20];

export default function ExitPctControl({
  stopLossPct,
  takeProfitPct,
  onStopLossChange,
  onTakeProfitChange,
  disabled,
  previewSlKrw,
  previewTpKrw,
}: Props) {
  return (
    <div className="exit-pct-control">
      <div className="exit-pct-row">
        <span className="exit-pct-title">손절 (평단 대비 하락 %)</span>
        <div className="exit-pct-presets">
          {SL_PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              className={`preset-btn ${Math.abs(stopLossPct - p) < 0.05 ? "active" : ""}`}
              disabled={disabled}
              onClick={() => onStopLossChange(p)}
            >
              -{p}%
            </button>
          ))}
        </div>
        <div className="exit-pct-input-row">
          <input
            type="range"
            min={0.5}
            max={25}
            step={0.5}
            value={stopLossPct}
            disabled={disabled}
            onChange={(e) => onStopLossChange(roundPct2(parseFloat(e.target.value)))}
          />
          <input
            type="number"
            className="exit-pct-num"
            min={0.1}
            max={50}
            step={0.1}
            value={stopLossPct}
            disabled={disabled}
            onChange={(e) =>
              onStopLossChange(roundPct2(parseFloat(e.target.value) || 1))
            }
          />
          <span className="exit-pct-unit">%</span>
        </div>
      </div>

      <div className="exit-pct-row">
        <span className="exit-pct-title">익절 (평단 대비 상승 %)</span>
        <div className="exit-pct-presets">
          {TP_PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              className={`preset-btn ${Math.abs(takeProfitPct - p) < 0.05 ? "active" : ""}`}
              disabled={disabled}
              onClick={() => onTakeProfitChange(p)}
            >
              +{p}%
            </button>
          ))}
        </div>
        <div className="exit-pct-input-row">
          <input
            type="range"
            min={0.5}
            max={50}
            step={0.5}
            value={takeProfitPct}
            disabled={disabled}
            onChange={(e) => onTakeProfitChange(roundPct2(parseFloat(e.target.value)))}
          />
          <input
            type="number"
            className="exit-pct-num"
            min={0.1}
            max={100}
            step={0.1}
            value={takeProfitPct}
            disabled={disabled}
            onChange={(e) =>
              onTakeProfitChange(roundPct2(parseFloat(e.target.value) || 1))
            }
          />
          <span className="exit-pct-unit">%</span>
        </div>
      </div>

      {(previewSlKrw != null && previewSlKrw > 0) ||
      (previewTpKrw != null && previewTpKrw > 0) ? (
        <p className="exit-plan-preview">
          적용 시 목표: 손절{" "}
          <strong>-{fmtPctSetting(stopLossPct)}</strong>
          {previewSlKrw != null && previewSlKrw > 0
            ? ` (약 ${Math.round(previewSlKrw).toLocaleString("ko-KR")}원)`
            : ""}
          {" · "}
          익절 <strong>+{fmtPctSetting(takeProfitPct)}</strong>
          {previewTpKrw != null && previewTpKrw > 0
            ? ` (약 ${Math.round(previewTpKrw).toLocaleString("ko-KR")}원)`
            : ""}
        </p>
      ) : null}
    </div>
  );
}

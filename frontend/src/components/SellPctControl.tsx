type Props = {
  value: number;
  onChange: (pct: number) => void;
  disabled?: boolean;
};

const OPTIONS = [10, 25, 50, 75, 100];

export default function SellPctControl({ value, onChange, disabled }: Props) {
  return (
    <div className="sell-pct-stack" role="group" aria-label="매도 비율">
      <span className="sell-pct-label">매도 비율</span>
      <div className="sell-pct-grid">
        {OPTIONS.map((p) => (
          <button
            key={p}
            type="button"
            className={`preset-btn preset-btn-stack ${value === p ? "active" : ""}`}
            disabled={disabled}
            onClick={() => onChange(p)}
          >
            <span className="preset-label">{p}%</span>
          </button>
        ))}
      </div>
    </div>
  );
}

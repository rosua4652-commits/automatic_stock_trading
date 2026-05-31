import type { BarItem } from "../../utils/chartData";

type Props = {
  items: BarItem[];
  title?: string;
  maxValue?: number;
  unit?: string;
};

export default function BarChart({ items, title, maxValue, unit = "" }: Props) {
  const max = maxValue ?? Math.max(1, ...items.map((i) => i.value));

  return (
    <div className="chart-bar-wrap">
      {title && <h4 className="chart-title">{title}</h4>}
      <ul className="chart-bar-list">
        {items.map((item) => (
          <li key={item.label} className="chart-bar-row">
            <span className="chart-bar-label">{item.label}</span>
            <div className="chart-bar-track">
              <div
                className="chart-bar-fill"
                style={{
                  width: `${Math.min(100, (item.value / max) * 100)}%`,
                  background: item.color || "var(--accent)",
                }}
              />
            </div>
            <span className="chart-bar-val">
              {item.value}
              {unit}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

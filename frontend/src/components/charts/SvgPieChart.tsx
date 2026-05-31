import type { PieSlice } from "../../utils/chartData";

type Props = {
  slices: PieSlice[];
  size?: number;
  title?: string;
  emptyText?: string;
};

function polar(cx: number, cy: number, r: number, deg: number) {
  const rad = ((deg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arcPath(
  cx: number,
  cy: number,
  r: number,
  startDeg: number,
  endDeg: number
): string {
  if (endDeg - startDeg >= 359.99) {
    return `M ${cx} ${cy - r} A ${r} ${r} 0 1 1 ${cx - 0.01} ${cy - r} Z`;
  }
  const s = polar(cx, cy, r, startDeg);
  const e = polar(cx, cy, r, endDeg);
  const large = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${cx} ${cy} L ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y} Z`;
}

export default function SvgPieChart({
  slices,
  size = 200,
  title,
  emptyText = "데이터 없음",
}: Props) {
  const total = slices.reduce((s, x) => s + x.value, 0);
  const cx = size / 2;
  const cy = size / 2;
  const r = size * 0.38;

  let angle = 0;
  const arcs = slices.map((sl) => {
    const sweep = total > 0 ? (sl.value / total) * 360 : 0;
    const start = angle;
    angle += sweep;
    return { ...sl, start, end: angle, path: arcPath(cx, cy, r, start, angle) };
  });

  return (
    <div className="chart-pie-wrap">
      {title && <h4 className="chart-title">{title}</h4>}
      <div className="chart-pie-body">
        {total <= 0 ? (
          <div className="chart-empty" style={{ width: size, height: size }}>
            {emptyText}
          </div>
        ) : (
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
            {arcs.map((a) => (
              <path
                key={a.id}
                d={a.path}
                fill={a.color}
                stroke="var(--bg)"
                strokeWidth={1.5}
              >
                <title>
                  {a.label}: {a.pct?.toFixed(1)}%
                </title>
              </path>
            ))}
            <circle cx={cx} cy={cy} r={r * 0.52} fill="var(--surface2)" />
          </svg>
        )}
        <ul className="chart-legend">
          {slices.map((s) => (
            <li key={s.id}>
              <span className="chart-legend-dot" style={{ background: s.color }} />
              <span className="chart-legend-label">{s.label}</span>
              <span className="chart-legend-val">
                {s.pct != null ? `${s.pct.toFixed(1)}%` : ""}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

type Props = {
  buys: number[];
  sells: number[];
  title?: string;
};

export default function HourlyActivityChart({ buys, sells, title }: Props) {
  const max = Math.max(1, ...buys, ...sells);
  const w = 520;
  const h = 120;
  const pad = 8;
  const colW = (w - pad * 2) / 24;

  return (
    <div className="chart-hourly-wrap">
      {title && <h4 className="chart-title">{title}</h4>}
      <svg
        className="chart-hourly-svg"
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="xMidYMid meet"
      >
        {Array.from({ length: 24 }, (_, i) => {
          const bx = pad + i * colW + colW * 0.1;
          const bw = colW * 0.35;
          const bH = ((buys[i] || 0) / max) * (h - 28);
          const sH = ((sells[i] || 0) / max) * (h - 28);
          return (
            <g key={i}>
              <rect
                x={bx}
                y={h - 20 - bH}
                width={bw}
                height={bH}
                fill="#3b9eff"
                opacity={0.9}
                rx={1}
              >
                <title>{`${i}시 매수 ${buys[i]}`}</title>
              </rect>
              <rect
                x={bx + bw + 2}
                y={h - 20 - sH}
                width={bw}
                height={sH}
                fill="#f87171"
                opacity={0.85}
                rx={1}
              >
                <title>{`${i}시 매도 ${sells[i]}`}</title>
              </rect>
              {i % 3 === 0 && (
                <text
                  x={bx + bw}
                  y={h - 4}
                  fill="var(--muted)"
                  fontSize="9"
                  textAnchor="middle"
                >
                  {i}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="chart-hourly-legend">
        <span>
          <i className="dot buy" /> 매수
        </span>
        <span>
          <i className="dot sell" /> 매도
        </span>
      </div>
    </div>
  );
}

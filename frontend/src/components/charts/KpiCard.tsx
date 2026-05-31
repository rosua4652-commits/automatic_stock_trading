type Props = {
  label: string;
  value: string;
  sub?: string;
  tone?: "up" | "down" | "neutral";
};

export default function KpiCard({ label, value, sub, tone = "neutral" }: Props) {
  return (
    <div className={`kpi-card tone-${tone}`}>
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      {sub && <span className="kpi-sub">{sub}</span>}
    </div>
  );
}

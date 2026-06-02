import { surgeTagLabel } from "../utils";

type Props = {
  symbol: string;
  surgeTags?: Record<string, string> | null;
  className?: string;
};

export default function SurgeTagBadge({ symbol, surgeTags, className = "" }: Props) {
  const info = surgeTagLabel(symbol, surgeTags);
  if (!info) return null;
  return (
    <span
      className={`surge-symbol-tag tag-${info.tag} ${className}`.trim()}
      title={info.tag === "surge" ? "급등주 분류" : "하락주 분류"}
    >
      {info.label}
    </span>
  );
}

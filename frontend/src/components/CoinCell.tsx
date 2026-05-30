import type { ReactNode } from "react";
import type { CoinCandidate } from "../types";
import { entryBadge } from "../utils";

type Props = {
  name_ko: string;
  base: string;
  candidate?: CoinCandidate | null;
  held?: boolean;
  trailing?: ReactNode;
  compact?: boolean;
};

export default function CoinCell({
  name_ko,
  base,
  candidate,
  held,
  trailing,
  compact,
}: Props) {
  const entry = entryBadge(candidate ?? undefined);
  const entryLabel =
    entry.kind === "ok"
      ? "진입 가능"
      : entry.kind === "scalp"
        ? "단타 가능"
        : entry.kind === "hold"
          ? "진입 보류"
          : "";

  return (
    <div className={`coin-cell ${compact ? "compact" : ""}`}>
      <div className="coin-cell-text">
        <span className="coin-cell-name">{name_ko}</span>
        <span className="coin-cell-base">{base}</span>
        {entryLabel && (
          <span className={`coin-cell-entry ${entry.kind}`}>{entryLabel}</span>
        )}
      </div>
      {(trailing || held) && (
        <div className="coin-cell-side">
          {held && <span className="coin-cell-held">보유</span>}
          {trailing}
        </div>
      )}
    </div>
  );
}

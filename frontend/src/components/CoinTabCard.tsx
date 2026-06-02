import type { CoinCandidate, Portfolio, TabQuote } from "../types";
import { coinTabDisplay, fmtKrw, fmtPct, fmtVolumeKrw, resolveCoinMeta } from "../utils";
import SurgeTagBadge from "./SurgeTagBadge";

type Props = {
  symbol: string;
  portfolio: Portfolio;
  candidates: CoinCandidate[];
  quote?: TabQuote;
  selected?: boolean;
  surgeTags?: Record<string, string>;
};

export default function CoinTabCard({
  symbol,
  portfolio,
  candidates,
  quote,
  selected,
  surgeTags,
}: Props) {
  const meta = resolveCoinMeta(symbol, portfolio, candidates);
  const info = coinTabDisplay(symbol, portfolio, quote);

  return (
    <div className={`coin-tab-card ${selected ? "selected" : ""} ${info.held ? "held" : ""}`}>
      <span className="ctc-name">
        {meta.name_ko}
        <SurgeTagBadge symbol={symbol} surgeTags={surgeTags} className="ctc-tag" />
      </span>
      <span className="ctc-base">{meta.base}</span>
      {info.held && info.avgKrw != null && (
        <span className="ctc-row dim">평단가 {fmtKrw(info.avgKrw)}</span>
      )}
      {info.currentKrw != null && info.currentKrw > 0 && (
        <span className="ctc-row">현재가 {fmtKrw(info.currentKrw)}</span>
      )}
      {info.pnlPct != null && (
        <span className={`ctc-pnl ${info.pnlPct >= 0 ? "up" : "down"}`}>
          {fmtPct(info.pnlPct)}
        </span>
      )}
      {info.pnlPct == null && info.change24h != null && (
        <span className={`ctc-pnl ${info.change24h >= 0 ? "up" : "down"}`}>
          {fmtPct(info.change24h)}
        </span>
      )}
      {info.volume24hKrw != null && info.volume24hKrw > 0 && (
        <span className="ctc-row ctc-vol">거래량 {fmtVolumeKrw(info.volume24hKrw)}</span>
      )}
    </div>
  );
}

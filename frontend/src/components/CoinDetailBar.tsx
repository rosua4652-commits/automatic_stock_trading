import type { CoinView } from "../types";
import { entryBadge, fmtKrw, fmtPct, fmtUsd, isRunning } from "../utils";
import CoinTradeBar from "./CoinTradeBar";

type Props = {
  view: CoinView;
  botStatus: string;
  botMessage: string;
  canTrade: boolean;
  busy: boolean;
  cashKrw: number;
  recommendation?: import("../types").InvestmentRecommendation | null;
  onBuy: (symbol: string, amountKrw: number) => Promise<void>;
  onSell: (symbol: string, percent: number) => Promise<void>;
};

export default function CoinDetailBar({
  view,
  botStatus,
  botMessage,
  canTrade,
  busy,
  cashKrw,
  recommendation,
  onBuy,
  onSell,
}: Props) {
  const { meta, price_usdt, change_24h, in_portfolio, position, candidate } = view;
  const running = isRunning(botStatus);
  const entry = entryBadge(candidate ?? undefined);

  return (
    <div className="coin-detail-wrap">
      <div className="coin-detail coin-detail-compact">
        <div className="coin-detail-top">
          <div className="coin-detail-names">
            <h2 className="coin-title">{meta.name_ko}</h2>
            <span className="coin-pair">{meta.base}</span>
            {entry.kind !== "none" && (
              <span className={`coin-entry-chip ${entry.kind}`}>{entry.label}</span>
            )}
          </div>
          <div className="coin-detail-prices">
            <span className="coin-price">${fmtUsd(price_usdt)}</span>
            <span className={`coin-chg ${change_24h >= 0 ? "up" : "down"}`}>
              {fmtPct(change_24h)}
            </span>
          </div>
          <span className={`bot-status-pill ${running ? "on" : ""}`}>
            {running ? "분석 중" : "수동"}
          </span>
        </div>

        {in_portfolio && position && (
          <div className="coin-detail-hold">
            <span>원금 {fmtKrw(position.cost_basis_krw)}원</span>
            <span className={position.pnl_krw >= 0 ? "up" : "down"}>
              {position.pnl_krw >= 0 ? "+" : ""}
              {fmtKrw(position.pnl_krw)}원 ({fmtPct(position.pnl_pct)})
            </span>
          </div>
        )}

        {!in_portfolio && candidate && (
          <p className="coin-detail-mini" title={candidate.entry_detail}>
            시장 {candidate.score} · 차트 {candidate.entry_score}
            {candidate.entry_outlook ? ` · ${candidate.entry_outlook}` : ""}
          </p>
        )}

        {running && botMessage && (
          <p className="coin-detail-mini dim" title={botMessage}>
            {botMessage.length > 48 ? `${botMessage.slice(0, 48)}…` : botMessage}
          </p>
        )}
      </div>

      <CoinTradeBar
        view={view}
        canTrade={canTrade}
        running={running}
        busy={busy}
        cashKrw={cashKrw}
        recommendation={recommendation}
        onBuy={onBuy}
        onSell={onSell}
      />
    </div>
  );
}

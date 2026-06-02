import type { AppConfig, CoinView, InvestmentRecommendation, TabQuote } from "../types";
import {
  entryBadge,
  fmtKrw,
  fmtPct,
  fmtUsd,
  fmtVolumeKrw,
  isRunning,
  getAutoMinBuyKrw,
  getManualMinBuyKrw,
  fmtPctSetting,
  positionTpSl,
  recommendationTpSl,
} from "../utils";
import CoinTradeBar from "./CoinTradeBar";
import SurgeTagBadge from "./SurgeTagBadge";

type Props = {
  view: CoinView;
  botStatus: string;
  botMessage: string;
  canTrade: boolean;
  busy: boolean;
  cashKrw: number;
  config: AppConfig;
  recommendation?: InvestmentRecommendation | null;
  tabQuote?: TabQuote;
  surgeTags?: Record<string, string>;
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
  config,
  recommendation,
  tabQuote,
  surgeTags,
  onBuy,
  onSell,
}: Props) {
  const { meta, price_usdt, change_24h, in_portfolio, position, candidate } = view;
  const running = isRunning(botStatus);
  const entry = entryBadge(candidate ?? undefined);
  const autoMinBuy = getAutoMinBuyKrw(config);
  const manualMinBuy = getManualMinBuyKrw();

  const heldTpSl = position ? positionTpSl(position) : null;
  const previewAmt =
    recommendation && recommendation.amount_krw >= autoMinBuy
      ? recommendation.amount_krw
      : 0;
  const previewTpSl =
    !in_portfolio && previewAmt > 0
      ? recommendationTpSl(
          recommendation,
          price_usdt,
          previewAmt,
          config.stop_loss_pct,
          config.take_profit_pct
        )
      : null;
  const tpSl = heldTpSl?.hasLevels ? heldTpSl : previewTpSl?.hasLevels ? previewTpSl : null;
  const tpSlAuto = !!position && position.auto_quantity > 0 && position.stop_loss > 0;

  return (
    <div className="coin-detail-wrap">
      <div className="coin-detail coin-detail-compact">
        <div className="coin-detail-top">
          <div className="coin-detail-names">
            <h2 className="coin-title">
              {meta.name_ko}
              <SurgeTagBadge symbol={meta.symbol} surgeTags={surgeTags} className="inline-tag" />
            </h2>
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
            {tabQuote && (tabQuote.volume_24h_krw ?? 0) > 0 && (
              <span className="coin-vol" title="24시간 거래대금 (업비트)">
                거래량 {fmtVolumeKrw(tabQuote.volume_24h_krw!)}
              </span>
            )}
          </div>
          <span className={`bot-status-pill ${running ? "on" : ""}`}>
            {running ? "분석 중" : "수동"}
          </span>
        </div>

        {in_portfolio && position && (
          <div className="coin-detail-hold">
            {position.auto_quantity > 0 && !position.excluded_from_auto && (
              <span className="coin-auto-badge">AI 자동투자 · 익절/손절 감시</span>
            )}
            <span>원금 {fmtKrw(position.cost_basis_krw)}원</span>
            <span className={position.pnl_krw >= 0 ? "up" : "down"}>
              {position.pnl_krw >= 0 ? "+" : ""}
              {fmtKrw(position.pnl_krw)}원 ({fmtPct(position.pnl_pct)})
            </span>
          </div>
        )}

        {in_portfolio && position && position.auto_quantity > 0 && !position.excluded_from_auto && (
          <p className="coin-detail-mini">
            AI 수익률 {fmtPct(position.auto_pnl_pct)} / 익절 목표 +
            {fmtPctSetting(config.take_profit_pct)} · 손절 -
            {fmtPctSetting(config.stop_loss_pct)}
          </p>
        )}

        {tpSl && (
          <div className="coin-detail-tpsl">
            <span className="tpsl-tag">
              {in_portfolio
                ? tpSlAuto
                  ? "자동 익절·손절"
                  : "익절·손절 기준"
                : "승인 시 익절·손절"}
            </span>
            <span className="tpsl-line">
              <span className="up">
                익절 +{fmtKrw(tpSl.take_profit_krw)}원
                {tpSl.take_profit > 0 ? ` ($${fmtUsd(tpSl.take_profit)})` : ""}
              </span>
              <span className="tpsl-sep">/</span>
              <span className="down">
                손절 -{fmtKrw(tpSl.stop_loss_krw)}원
                {tpSl.stop_loss > 0 ? ` ($${fmtUsd(tpSl.stop_loss)})` : ""}
              </span>
            </span>
          </div>
        )}

        {in_portfolio && position && !heldTpSl?.hasLevels && (
          <p className="coin-detail-mini dim">수동 매수 — 익절·손절 자동 없음</p>
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
        minBuyKrw={manualMinBuy}
        recommendation={recommendation}
        onBuy={onBuy}
        onSell={onSell}
      />
    </div>
  );
}

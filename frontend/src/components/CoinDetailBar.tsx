import type { CoinView } from "../types";
import { fmtKrw, fmtPct, fmtUsd, isRunning } from "../utils";
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

  return (
    <div className="coin-detail-wrap">
      <div className="coin-detail">
        <div className="coin-detail-main">
          <h2 className="coin-title">{meta.name_ko}</h2>
          <span className="coin-en">{meta.name_en}</span>
          <span className="coin-pair">{meta.pair_label}</span>
        </div>
        <div className="coin-detail-stats">
          <div className="detail-stat">
            <span className="ds-label">현재가</span>
            <span className="ds-value">${fmtUsd(price_usdt)}</span>
          </div>
          <div className="detail-stat">
            <span className="ds-label">24h</span>
            <span className={`ds-value ${change_24h >= 0 ? "up" : "down"}`}>
              {fmtPct(change_24h)}
            </span>
          </div>
          {in_portfolio && position && (
            <>
              <div className="detail-stat">
                <span className="ds-label">평단가</span>
                <span className="ds-value">${fmtUsd(position.avg_price)}</span>
              </div>
              <div className="detail-stat">
                <span className="ds-label">보유량</span>
                <span className="ds-value">{position.quantity.toFixed(6)}</span>
              </div>
              <div className="detail-stat">
                <span className="ds-label">원금</span>
                <span className="ds-value">{fmtKrw(position.cost_basis_krw)}원</span>
              </div>
              <div className="detail-stat">
                <span className="ds-label">평가손익</span>
                <span className={`ds-value ${position.pnl_krw >= 0 ? "up" : "down"}`}>
                  {fmtKrw(position.pnl_krw)}원 ({fmtPct(position.pnl_pct)})
                </span>
              </div>
              <div className="detail-stat">
                <span className="ds-label">비중</span>
                <span className="ds-value">{position.weight_pct.toFixed(1)}%</span>
              </div>
            </>
          )}
          {!in_portfolio && candidate && (
            <>
              <div className="detail-stat">
                <span className="ds-label">시장점수</span>
                <span className="ds-value accent">{candidate.score}</span>
              </div>
              <div className="detail-stat">
                <span className="ds-label">차트점수</span>
                <span className={`ds-value ${candidate.entry_ok ? "up" : ""}`}>
                  {candidate.entry_score} {candidate.entry_ok ? "✓" : ""}
                </span>
              </div>
              <div className="detail-stat">
                <span className="ds-label">전망</span>
                <span className="ds-value">{candidate.entry_outlook || candidate.trend}</span>
              </div>
            </>
          )}
        </div>
        <div className="coin-detail-status">
          <span className={`bot-status-text ${running ? "on" : ""}`}>
            {botStatus === "stopping"
              ? "중지 중..."
              : running
                ? "자동투자 ON"
                : "수동관리 가능"}
          </span>
          {botMessage && <span className="bot-status-msg">{botMessage}</span>}
        </div>
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

import type { CoinView } from "../types";
import { fmtPct, fmtUsd, isRunning } from "../utils";

type Props = {
  view: CoinView;
  botStatus: string;
  botMessage: string;
};

export default function CoinDetailBar({ view, botStatus, botMessage }: Props) {
  const { meta, price_usdt, change_24h, in_portfolio, position, candidate } = view;
  const running = isRunning(botStatus);

  return (
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
              <span className="ds-label">수익률</span>
              <span className={`ds-value ${position.pnl_pct >= 0 ? "up" : "down"}`}>
                {fmtPct(position.pnl_pct)}
              </span>
            </div>
            <div className="detail-stat">
              <span className="ds-label">손절</span>
              <span className="ds-value dim">${fmtUsd(position.stop_loss)}</span>
            </div>
            <div className="detail-stat">
              <span className="ds-label">익절</span>
              <span className="ds-value dim">${fmtUsd(position.take_profit)}</span>
            </div>
          </>
        )}
        {!in_portfolio && candidate && (
          <>
            <div className="detail-stat">
              <span className="ds-label">AI점수</span>
              <span className="ds-value accent">{candidate.score}</span>
            </div>
            <div className="detail-stat">
              <span className="ds-label">추세</span>
              <span className="ds-value">{candidate.trend}</span>
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
              : "자동투자 OFF"}
        </span>
        {botMessage && <span className="bot-status-msg">{botMessage}</span>}
      </div>
    </div>
  );
}

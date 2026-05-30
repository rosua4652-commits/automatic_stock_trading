import { useEffect, useState } from "react";
import type {
  Portfolio,
  Position,
  TradeEvent,
  UpbitAccountSnapshot,
} from "../types";
import { fmtKrw, fmtPct, fmtUsd, isRunning, MIN_BUY_KRW } from "../utils";
import BuyAmountControl, { maxBuyKrw } from "./BuyAmountControl";
import SellPctControl from "./SellPctControl";

type Props = {
  portfolio: Portfolio;
  trades: TradeEvent[];
  botStatus: string;
  manualMode: boolean;
  tradeMode?: "paper" | "live";
  upbitSnapshot?: UpbitAccountSnapshot | null;
  onManualBuy: (symbol: string, amountKrw: number) => Promise<void>;
  onManualSell: (symbol: string, percent: number) => Promise<void>;
  onSellAll?: () => void;
  onSelectChart: (symbol: string) => void;
  onExclude: (symbol: string, exclude: boolean) => Promise<void>;
  busy: boolean;
};

function fmtQty(q: number) {
  if (q >= 1) return q.toLocaleString("en-US", { maximumFractionDigits: 4 });
  return q.toLocaleString("en-US", { maximumFractionDigits: 8 });
}

function fmtTime(ts: number) {
  return new Date(ts * 1000).toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function PositionCard({
  pos,
  canTrade,
  busy,
  onSell,
  onChart,
  onExclude,
}: {
  pos: Position;
  canTrade: boolean;
  busy: boolean;
  onSell: (pct: number) => void;
  onChart: () => void;
  onExclude: (exclude: boolean) => void;
}) {
  const [sellPct, setSellPct] = useState(100);

  return (
    <div className="fund-card">
      <div className="fund-card-head">
        <div>
          <h4>{pos.name_ko}</h4>
          <span className="fund-pair">{pos.pair_label}</span>
          {pos.auto_quantity > 0 && (
            <span className="badge auto">AI {fmtQty(pos.auto_quantity)}</span>
          )}
          {pos.manual_quantity > 0 && (
            <span className="badge manual">수동 {fmtQty(pos.manual_quantity)}</span>
          )}
          {pos.excluded_from_auto && (
            <span className="badge exclude">자동투자 제외</span>
          )}
        </div>
        <button type="button" className="link-btn" onClick={onChart}>
          차트 보기
        </button>
      </div>

      <div className="fund-grid">
        <div className="fg-item">
          <span className="fg-label">총 수량</span>
          <span className="fg-val">{fmtQty(pos.quantity)}</span>
        </div>
        <div className="fg-item">
          <span className="fg-label">AI / 수동</span>
          <span className="fg-val dim">
            {fmtQty(pos.auto_quantity)} / {fmtQty(pos.manual_quantity)}
          </span>
        </div>
        <div className="fg-item">
          <span className="fg-label">평단가</span>
          <span className="fg-val">
            {pos.data_source === "upbit" && (pos.avg_buy_price_krw ?? 0) > 0
              ? `${fmtKrw(pos.avg_buy_price_krw!)}원`
              : `$${fmtUsd(pos.avg_price)}`}
          </span>
        </div>
        <div className="fg-item">
          <span className="fg-label">현재가</span>
          <span className="fg-val">
            {pos.data_source === "upbit" && (pos.current_price_krw ?? 0) > 0
              ? `${fmtKrw(pos.current_price_krw!)}원`
              : `$${fmtUsd(pos.current_price)}`}
          </span>
        </div>
        {pos.data_source === "upbit" && (
          <div className="fg-item">
            <span className="fg-label">업비트 수량</span>
            <span className="fg-val">{fmtQty(pos.exchange_quantity ?? pos.quantity)}</span>
          </div>
        )}
        <div className="fg-item">
          <span className="fg-label">원금 (매수금액)</span>
          <span className="fg-val">{fmtKrw(pos.cost_basis_krw)}원</span>
        </div>
        <div className="fg-item">
          <span className="fg-label">평가금액</span>
          <span className="fg-val">{fmtKrw(pos.current_value_krw)}원</span>
        </div>
        <div className="fg-item">
          <span className="fg-label">평가손익</span>
          <span className={`fg-val ${pos.pnl_krw >= 0 ? "up" : "down"}`}>
            {pos.pnl_krw >= 0 ? "+" : ""}
            {fmtKrw(pos.pnl_krw)}원 ({fmtPct(pos.pnl_pct)})
          </span>
        </div>
        <div className="fg-item">
          <span className="fg-label">자산 비중</span>
          <span className="fg-val">{pos.weight_pct.toFixed(1)}%</span>
        </div>
        <div className="fg-item">
          <span className="fg-label">손절 / 익절</span>
          <span className="fg-val dim">
            ${fmtUsd(pos.stop_loss)} / ${fmtUsd(pos.take_profit)}
          </span>
        </div>
      </div>

      {pos.entry_reason && (
        <p className="entry-reason">
          <strong>진입 근거:</strong> {pos.entry_reason}
          {pos.entry_score > 0 && ` (차트점수 ${pos.entry_score})`}
        </p>
      )}

      <label className="exclude-row checkbox-field">
        <input
          type="checkbox"
          checked={pos.excluded_from_auto}
          disabled={busy}
          onChange={(e) => onExclude(e.target.checked)}
        />
        <span>
          자동투자 제외
          <span className="exclude-hint dim">
            {pos.excluded_from_auto
              ? " — 체크됨: AI 익절·손절 안 함"
              : pos.auto_quantity > 0
                ? " — 해제(기본): AI가 익절·손절 감시"
                : " — 수동 매수분만 해당"}
          </span>
        </span>
      </label>

      {canTrade && (
        <div className="manual-sell-row sell-block-stack">
          <SellPctControl value={sellPct} onChange={setSellPct} disabled={busy} />
          <button
            type="button"
            className="btn-sell sell-submit-btn"
            disabled={busy}
            onClick={() => onSell(sellPct)}
          >
            {sellPct}% 매도
          </button>
        </div>
      )}
    </div>
  );
}

function fmtSyncTime(ts?: number) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function FundsTab({
  portfolio,
  trades,
  botStatus,
  manualMode,
  tradeMode = "paper",
  upbitSnapshot,
  onManualBuy,
  onManualSell,
  onSellAll,
  onSelectChart,
  onExclude,
  busy,
}: Props) {
  const [buySymbol, setBuySymbol] = useState("BTCUSDT");
  const [buyAmount, setBuyAmount] = useState(500_000);
  const running = isRunning(botStatus);
  const canTrade = botStatus !== "stopping";
  const maxKrw = maxBuyKrw(portfolio.cash_krw);

  useEffect(() => {
    setBuyAmount((prev) => Math.min(prev, maxKrw));
  }, [maxKrw]);

  return (
    <div className="funds-tab">
      {running && (
        <div className="funds-notice warn">
          분석 실행 중 — 매수는 「AI 투자 제안」 승인 또는 아래 수동 매매를 이용하세요.
        </div>
      )}
      {canTrade && (
        <div className="funds-notice ok">
          수동 관리 모드 · 원하는 만큼 매수/매도할 수 있습니다. (자동투자 중지 상태)
        </div>
      )}
      {tradeMode === "live" && (
        <div className="funds-notice ok">
          <strong>업비트 API 기준</strong> — 잔고·수량·평단·시세·평가·총자산은 업비트 계정/시세와
          동기화됩니다
          {upbitSnapshot?.synced_at
            ? ` · 마지막 동기화 ${fmtSyncTime(upbitSnapshot.synced_at)}`
            : portfolio.upbit_synced_at
              ? ` · 마지막 동기화 ${fmtSyncTime(portfolio.upbit_synced_at)}`
              : ""}
          {upbitSnapshot && (
            <span className="exclude-hint dim">
              {" "}
              (총자산 {fmtKrw(upbitSnapshot.total_assets_krw)}원 = KRW{" "}
              {fmtKrw(upbitSnapshot.krw_balance)} + 코인 {fmtKrw(upbitSnapshot.coin_valuation_krw)}
              )
            </span>
          )}
        </div>
      )}

      {canTrade && (
        <section className="funds-manual-buy">
          <h3>수동 매수</h3>
          <div className="buy-form">
            <label>
              코인 심볼
              <input
                type="text"
                value={buySymbol}
                onChange={(e) => setBuySymbol(e.target.value.toUpperCase())}
                placeholder="BTCUSDT"
              />
            </label>
            <BuyAmountControl
              id="funds-buy-amount"
              cashKrw={portfolio.cash_krw}
              value={buyAmount}
              onChange={setBuyAmount}
              disabled={busy}
            />
            <button
              type="button"
              className="btn-primary buy-submit-btn"
              disabled={
                busy ||
                buyAmount < MIN_BUY_KRW ||
                buyAmount > portfolio.cash_krw
              }
              onClick={() => onManualBuy(buySymbol, buyAmount)}
            >
              매수 ({fmtKrw(buyAmount)}원)
            </button>
          </div>
        </section>
      )}

      <section className="funds-positions">
        <div className="panel-block-head">
          <h3>보유 코인 상세</h3>
          {portfolio.positions.length > 0 && canTrade && onSellAll && (
            <button
              type="button"
              className="btn-sell-all"
              disabled={busy}
              onClick={onSellAll}
            >
              전체 매도 (100%)
            </button>
          )}
        </div>
        {portfolio.positions.length === 0 ? (
          <p className="empty">보유 중인 코인이 없습니다</p>
        ) : (
          portfolio.positions.map((p) => (
            <PositionCard
              key={p.symbol}
              pos={p}
              canTrade={canTrade}
              busy={busy}
              onSell={(pct) => onManualSell(p.symbol, pct)}
              onChart={() => onSelectChart(p.symbol)}
              onExclude={(ex) => onExclude(p.symbol, ex)}
            />
          ))
        )}
      </section>

      <section className="funds-trades">
        <h3>매매 내역</h3>
        <div className="trades-table-wrap">
          <table className="trades-table">
            <thead>
              <tr>
                <th>시간</th>
                <th>코인</th>
                <th>구분</th>
                <th>단가</th>
                <th>수량</th>
                <th>체결금액</th>
                <th>사유</th>
              </tr>
            </thead>
            <tbody>
              {trades.length === 0 ? (
                <tr>
                  <td colSpan={7} className="empty-cell">
                    체결 내역 없음
                  </td>
                </tr>
              ) : (
                trades
                  .slice()
                  .reverse()
                  .map((t, i) => (
                    <tr key={`${t.ts}-${i}`} className={t.side === "BUY" ? "buy" : "sell"}>
                      <td>{fmtTime(t.ts)}</td>
                      <td>{t.display}</td>
                      <td>{t.side === "BUY" ? "매수" : "매도"}</td>
                      <td>${fmtUsd(t.price)}</td>
                      <td>{fmtQty(t.quantity)}</td>
                      <td>{fmtKrw(t.amount_krw)}원</td>
                      <td>{t.reason}</td>
                    </tr>
                  ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

import { useEffect, useState } from "react";
import type { CoinView, InvestmentRecommendation } from "../types";
import BuyAmountControl, { maxBuyKrw } from "./BuyAmountControl";
import { fmtKrw, fmtUsd, MIN_BUY_KRW } from "../utils";

type Props = {
  view: CoinView;
  canTrade: boolean;
  running: boolean;
  busy: boolean;
  cashKrw: number;
  recommendation?: InvestmentRecommendation | null;
  onBuy: (symbol: string, amountKrw: number) => Promise<void>;
  onSell: (symbol: string, percent: number) => Promise<void>;
};

export default function CoinTradeBar({
  view,
  canTrade,
  running,
  busy,
  cashKrw,
  recommendation,
  onBuy,
  onSell,
}: Props) {
  const recAmt =
    recommendation && recommendation.amount_krw >= MIN_BUY_KRW
      ? recommendation.amount_krw
      : null;
  const [amount, setAmount] = useState(() =>
    Math.min(recAmt ?? 500_000, maxBuyKrw(cashKrw))
  );
  const [sellPct, setSellPct] = useState(100);
  const sym = view.meta.symbol;
  const held = view.in_portfolio && view.position;
  const maxKrw = maxBuyKrw(cashKrw);

  useEffect(() => {
    if (recAmt) {
      setAmount(Math.min(recAmt, maxKrw));
    } else {
      setAmount((prev) => Math.min(prev, maxKrw));
    }
  }, [maxKrw, sym, recAmt]);

  const canBuy =
    canTrade && !busy && amount >= MIN_BUY_KRW && amount <= cashKrw && cashKrw >= MIN_BUY_KRW;

  return (
    <div className="coin-trade-bar">
      {view.candidate?.entry_detail && (
        <p
          className={`entry-detail-box ${
            view.candidate.entry_ok
              ? "ok"
              : view.candidate.entry_scalp_ok
                ? "scalp"
                : "warn"
          }`}
        >
          {view.candidate.entry_detail}
        </p>
      )}
      {held && view.position?.entry_reason && (
        <p className="entry-detail-box ok">
          <strong>보유 근거:</strong> {view.position.entry_reason}
        </p>
      )}

      {recommendation && recAmt && (
        <p className="entry-detail-box ok">
          <strong>AI 제안:</strong> {fmtKrw(recAmt)}원
          {recommendation.price_usdt && recommendation.price_usdt > 0 && (
            <>
              {" "}
              · ${fmtUsd(recommendation.price_usdt)}에 약{" "}
              {(recommendation.quantity_est ?? 0).toFixed(4)}개
            </>
          )}
        </p>
      )}

      {running && (
        <p className="trade-hint subtle">
          분석 중에도 아래에서 즉시 매수 가능 · 제안은 우측 상단 알림
        </p>
      )}

      <div className="coin-trade-actions">
        <BuyAmountControl
          id={`buy-${sym}`}
          cashKrw={cashKrw}
          value={amount}
          onChange={setAmount}
          disabled={!canTrade || busy}
        />
        <button
          type="button"
          className="btn-primary btn-sm buy-submit-btn"
          disabled={!canBuy}
          onClick={() => onBuy(sym, amount)}
        >
          매수 ({fmtKrw(amount)}원)
        </button>
        {held && (
          <div className="sell-block">
            <label className="sell-range-label">
              매도 비율
              <input
                type="range"
                min={10}
                max={100}
                step={10}
                value={sellPct}
                disabled={!canTrade || busy}
                onChange={(e) => setSellPct(Number(e.target.value))}
              />
              <span>{sellPct}%</span>
            </label>
            <button
              type="button"
              className="btn-sell btn-sm"
              disabled={!canTrade || busy}
              onClick={() => onSell(sym, sellPct)}
            >
              매도
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

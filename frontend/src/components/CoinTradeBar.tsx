import { useEffect, useState } from "react";
import type { CoinView, InvestmentRecommendation } from "../types";
import BuyAmountControl, { maxBuyKrw } from "./BuyAmountControl";
import SellPctControl from "./SellPctControl";
import { fmtKrw } from "../utils";

type Props = {
  view: CoinView;
  canTrade: boolean;
  running: boolean;
  busy: boolean;
  cashKrw: number;
  minBuyKrw?: number;
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
  minBuyKrw = 10_000,
  recommendation,
  onBuy,
  onSell,
}: Props) {
  const minBuy = Math.max(5_000, Math.round(minBuyKrw / 1000) * 1000);
  const recAmt =
    recommendation && recommendation.amount_krw >= minBuy
      ? recommendation.amount_krw
      : null;
  const [amount, setAmount] = useState(() =>
    Math.min(recAmt ?? 500_000, maxBuyKrw(cashKrw, minBuy))
  );
  const [sellPct, setSellPct] = useState(100);
  const sym = view.meta.symbol;
  const held = view.in_portfolio && view.position;
  const maxKrw = maxBuyKrw(cashKrw, minBuy);

  useEffect(() => {
    if (recAmt) {
      setAmount(Math.min(recAmt, maxKrw));
    } else {
      setAmount((prev) => Math.min(prev, maxKrw));
    }
  }, [maxKrw, sym, recAmt]);

  const canBuy =
    canTrade && !busy && amount >= minBuy && amount <= cashKrw && cashKrw >= minBuy;

  const entryLine = view.candidate?.entry_detail;
  const shortEntry =
    entryLine && entryLine.length > 72 ? `${entryLine.slice(0, 72)}…` : entryLine;

  return (
    <div className="coin-trade-bar coin-trade-bar-compact">
      {shortEntry && !held && (
        <p
          className={`entry-detail-box compact ${
            view.candidate?.entry_ok
              ? "ok"
              : view.candidate?.entry_scalp_ok
                ? "scalp"
                : "warn"
          }`}
          title={view.candidate?.entry_detail}
        >
          {shortEntry}
        </p>
      )}

      {recAmt && !held && (
        <p className="rec-inline-hint">
          AI 제안 {fmtKrw(recAmt)}원 · 승인 매수는 익절/손절 자동
        </p>
      )}

      <div className="coin-trade-actions">
        <BuyAmountControl
          id={`buy-${sym}`}
          cashKrw={cashKrw}
          value={amount}
          onChange={setAmount}
          disabled={!canTrade || busy}
          minBuyKrw={minBuy}
        />
        <button
          type="button"
          className="btn-primary btn-sm buy-submit-btn"
          disabled={!canBuy}
          onClick={() => onBuy(sym, amount)}
        >
          매수 {fmtKrw(amount)}원
        </button>
        {held && (
          <div className="sell-block sell-block-stack">
            <SellPctControl
              value={sellPct}
              onChange={setSellPct}
              disabled={!canTrade || busy}
            />
            <button
              type="button"
              className="btn-sell btn-sm sell-submit-btn"
              disabled={!canTrade || busy}
              onClick={() => onSell(sym, sellPct)}
            >
              {sellPct}% 매도
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

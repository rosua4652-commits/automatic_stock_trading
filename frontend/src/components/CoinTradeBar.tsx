import { useEffect, useState } from "react";
import type { CoinView } from "../types";
import BuyAmountControl, { maxBuyKrw } from "./BuyAmountControl";
import { fmtKrw, MIN_BUY_KRW } from "../utils";

type Props = {
  view: CoinView;
  canTrade: boolean;
  running: boolean;
  busy: boolean;
  cashKrw: number;
  onBuy: (symbol: string, amountKrw: number) => Promise<void>;
  onSell: (symbol: string, percent: number) => Promise<void>;
};

export default function CoinTradeBar({
  view,
  canTrade,
  running,
  busy,
  cashKrw,
  onBuy,
  onSell,
}: Props) {
  const [amount, setAmount] = useState(() =>
    Math.min(500_000, maxBuyKrw(cashKrw))
  );
  const [sellPct, setSellPct] = useState(100);
  const sym = view.meta.symbol;
  const held = view.in_portfolio && view.position;
  const maxKrw = maxBuyKrw(cashKrw);

  useEffect(() => {
    setAmount((prev) => Math.min(prev, maxKrw));
  }, [maxKrw, sym]);

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

      {running && (
        <p className="trade-hint warn subtle">
          분석 실행 중 — 위 「AI 투자 제안」에서 선택 후 「승인 매수」하세요. 개별 매수도 가능합니다.
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

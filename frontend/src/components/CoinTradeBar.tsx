import { useState } from "react";
import type { CoinView } from "../types";
import { fmtKrw } from "../utils";

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
  const [amount, setAmount] = useState(500_000);
  const [sellPct, setSellPct] = useState(100);
  const sym = view.meta.symbol;
  const held = view.in_portfolio && view.position;

  return (
    <div className="coin-trade-bar">
      {view.candidate?.entry_detail && (
        <p className={`entry-detail-box ${view.candidate.entry_ok ? "ok" : "warn"}`}>
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
        <label>
          매수 금액 (원)
          <input
            type="number"
            min={50000}
            step={10000}
            value={amount}
            disabled={!canTrade || busy}
            onChange={(e) => setAmount(Number(e.target.value))}
          />
        </label>
        <button
          type="button"
          className="btn-primary btn-sm"
          disabled={!canTrade || busy || amount > cashKrw}
          onClick={() => onBuy(sym, amount)}
        >
          매수
        </button>
        {held && (
          <>
            <label>
              매도 %
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
          </>
        )}
      </div>
      {canTrade && amount > cashKrw && (
        <p className="trade-hint warn">현금 {fmtKrw(cashKrw)}원 — 잔고 부족</p>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import type {
  Portfolio,
  Position,
  TradeEvent,
  UpbitAccountSnapshot,
} from "../types";
import {
  fmtKrw,
  fmtPct,
  fmtPctSetting,
  fmtQty,
  tradeAmountKrw,
  tradeQuantity,
  tradeUnitPriceKrw,
  fmtUsd,
  gainPctFromAvg,
  isRunning,
  lossPctFromAvg,
  getMinBuyKrw,
  pctFromAvg,
  pricesFromExitPct,
  resolveEntryTier,
  roundPct2,
} from "../utils";
import BuyAmountControl, { maxBuyKrw } from "./BuyAmountControl";
import MinBuyKrwPanel from "./MinBuyKrwPanel";
import ExitPctControl from "./ExitPctControl";
import SellPctControl from "./SellPctControl";

type Props = {
  portfolio: Portfolio;
  trades: TradeEvent[];
  botStatus: string;
  manualMode: boolean;
  tradeMode?: "paper" | "live";
  tradesSyncError?: string;
  tradesDisplayCount?: number;
  tradesOrdersFetched?: number;
  upbitSnapshot?: UpbitAccountSnapshot | null;
  onManualBuy: (symbol: string, amountKrw: number) => Promise<void>;
  onManualSell: (symbol: string, percent: number) => Promise<void>;
  onSellAll?: () => void;
  onSelectChart: (symbol: string) => void;
  onExclude: (symbol: string, exclude: boolean) => Promise<void>;
  onExitPlan: (
    symbol: string,
    plan: {
      custom_sl_tp: boolean;
      stop_loss_pct?: number;
      take_profit_pct?: number;
    }
  ) => Promise<void>;
  onMigrateExits?: () => Promise<void>;
  stopLossPct: number;
  takeProfitPct: number;
  minBuyKrw?: number;
  onSaveMinBuyKrw?: (minBuyKrw: number) => Promise<void>;
  savingMinBuy?: boolean;
  busy: boolean;
};

function ExitDistanceGauges({
  current,
  stopLoss,
  takeProfit,
}: {
  current: number;
  stopLoss: number;
  takeProfit: number;
}) {
  const toTp = Math.max(0, ((takeProfit - current) / current) * 100);
  const toSl = Math.max(0, ((current - stopLoss) / current) * 100);
  const tpHit = current >= takeProfit * 0.999;
  const slHit = current <= stopLoss * 1.001;
  return (
    <div className="exit-gauges">
      <div className="exit-gauge-row">
        <span className="exit-gauge-label up">익절</span>
        <div className="exit-gauge-track">
          <div
            className="exit-gauge-fill up"
            style={{ width: `${Math.min(100, tpHit ? 100 : toTp * 5)}%` }}
          />
        </div>
        <span className="exit-gauge-pct up">
          {tpHit ? "도달" : `+${toTp.toFixed(2)}%`}
        </span>
      </div>
      <div className="exit-gauge-row">
        <span className="exit-gauge-label down">손절</span>
        <div className="exit-gauge-track">
          <div
            className="exit-gauge-fill down"
            style={{ width: `${Math.min(100, slHit ? 100 : toSl * 5)}%` }}
          />
        </div>
        <span className="exit-gauge-pct down">
          {slHit ? "도달" : `-${toSl.toFixed(2)}%`}
        </span>
      </div>
    </div>
  );
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
  onExitPlan,
  stopLossPct,
  takeProfitPct,
}: {
  pos: Position;
  canTrade: boolean;
  busy: boolean;
  onSell: (pct: number) => void;
  onChart: () => void;
  onExclude: (exclude: boolean) => void;
  onExitPlan: (
    plan: {
      custom_sl_tp: boolean;
      stop_loss_pct?: number;
      take_profit_pct?: number;
    }
  ) => Promise<void>;
  stopLossPct: number;
  takeProfitPct: number;
}) {
  const [sellPct, setSellPct] = useState(100);
  const [customSlTp, setCustomSlTp] = useState(!!pos.custom_sl_tp);

  const entry = pos.avg_price;
  const initSlPct =
    pos.custom_stop_loss_pct && pos.custom_stop_loss_pct > 0
      ? pos.custom_stop_loss_pct
      : lossPctFromAvg(entry, pos.stop_loss, stopLossPct);
  const initTpPct =
    pos.custom_take_profit_pct && pos.custom_take_profit_pct > 0
      ? pos.custom_take_profit_pct
      : gainPctFromAvg(entry, pos.take_profit, takeProfitPct);

  const [slPctIn, setSlPctIn] = useState(initSlPct);
  const [tpPctIn, setTpPctIn] = useState(initTpPct);

  useEffect(() => {
    setCustomSlTp(!!pos.custom_sl_tp);
    const e = pos.avg_price;
    setSlPctIn(
      pos.custom_stop_loss_pct && pos.custom_stop_loss_pct > 0
        ? pos.custom_stop_loss_pct
        : lossPctFromAvg(e, pos.stop_loss, stopLossPct)
    );
    setTpPctIn(
      pos.custom_take_profit_pct && pos.custom_take_profit_pct > 0
        ? pos.custom_take_profit_pct
        : gainPctFromAvg(e, pos.take_profit, takeProfitPct)
    );
  }, [
    pos.symbol,
    pos.custom_sl_tp,
    pos.stop_loss,
    pos.take_profit,
    pos.avg_price,
    pos.custom_stop_loss_pct,
    pos.custom_take_profit_pct,
    stopLossPct,
    takeProfitPct,
  ]);

  const preview =
    entry > 0 ? pricesFromExitPct(entry, slPctIn, tpPctIn) : null;
  const slPct = pctFromAvg(entry, pos.stop_loss);
  const tpPct = pctFromAvg(entry, pos.take_profit);
  const fxKrw =
    pos.current_price > 0 && (pos.current_price_krw ?? 0) > 0
      ? pos.current_price_krw! / pos.current_price
      : 0;
  const slKrw = fxKrw > 0 ? pos.stop_loss * fxKrw : 0;
  const tpKrw = fxKrw > 0 ? pos.take_profit * fxKrw : 0;

  const tier = resolveEntryTier(pos);

  const applyExitPlan = async (
    custom: boolean,
    slPct?: number,
    tpPct?: number
  ) => {
    await onExitPlan({
      custom_sl_tp: custom,
      stop_loss_pct: slPct != null ? roundPct2(slPct) : undefined,
      take_profit_pct: tpPct != null ? roundPct2(tpPct) : undefined,
    });
  };

  return (
    <div className="fund-card">
      <div className="fund-card-head">
        <div>
          <h4>{pos.name_ko}</h4>
          <span className="fund-pair">{pos.pair_label}</span>
          {pos.auto_quantity > 0 && (
            <span
              className={`badge auto${
                tier.kind === "scalp"
                  ? " tier-scalp"
                  : tier.kind === "long"
                    ? " tier-long"
                    : ""
              }`}
            >
              {tier.kind === "scalp" || tier.kind === "long"
                ? `${tier.label} AI `
                : "AI "}
              {fmtQty(pos.auto_quantity)}
            </span>
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
        {pos.current_price > 0 && pos.stop_loss > 0 && pos.take_profit > 0 && (
          <div className="fg-item fg-item-wide exit-gauge-block">
            <span className="fg-label">익절·손절까지</span>
            <ExitDistanceGauges
              current={pos.current_price}
              stopLoss={pos.stop_loss}
              takeProfit={pos.take_profit}
            />
          </div>
        )}
        <div className="fg-item fg-item-wide">
          <span className="fg-label">손절 / 익절</span>
          <span className="fg-val dim">
            {pos.data_source === "upbit" && slKrw > 0 ? (
              <>
                {fmtKrw(slKrw)}원{slPct != null ? ` (${fmtPct(slPct)})` : ""}
                {" / "}
                {fmtKrw(tpKrw)}원{tpPct != null ? ` (${fmtPct(tpPct)})` : ""}
              </>
            ) : (
              <>
                ${fmtUsd(pos.stop_loss)}
                {slPct != null ? ` (${fmtPct(slPct)})` : ""}
                {" / "}$
                {fmtUsd(pos.take_profit)}
                {tpPct != null ? ` (${fmtPct(tpPct)})` : ""}
              </>
            )}
          </span>
        </div>
      </div>

      <div className="exit-plan-block">
        <label className="exclude-row checkbox-field">
          <input
            type="checkbox"
            checked={customSlTp}
            disabled={busy}
            onChange={async (e) => {
              const on = e.target.checked;
              setCustomSlTp(on);
              await applyExitPlan(on, slPctIn, tpPctIn);
            }}
          />
          <span>
            손익절 수동 지정
            <span className="exclude-hint dim">
              {customSlTp
                ? " — 체크됨: 아래 % 도달 시 전량 자동 매도 (가격은 평단 기준 자동 계산)"
                : ` — 해제 시 설정 손절 ${fmtPctSetting(stopLossPct)} / 익절 ${fmtPctSetting(takeProfitPct)} 자동`}
            </span>
          </span>
        </label>
        {customSlTp && (
          <div className="exit-plan-inputs">
            <ExitPctControl
              stopLossPct={slPctIn}
              takeProfitPct={tpPctIn}
              onStopLossChange={setSlPctIn}
              onTakeProfitChange={setTpPctIn}
              disabled={busy}
              previewSlKrw={
                preview && fxKrw > 0 ? preview.stop_loss * fxKrw : undefined
              }
              previewTpKrw={
                preview && fxKrw > 0 ? preview.take_profit * fxKrw : undefined
              }
            />
            <button
              type="button"
              className="btn-primary exit-pct-apply"
              disabled={busy || slPctIn <= 0 || tpPctIn <= 0 || entry <= 0}
              onClick={() => applyExitPlan(true, slPctIn, tpPctIn)}
            >
              손절 -{fmtPctSetting(slPctIn)} / 익절 +{fmtPctSetting(tpPctIn)} 적용
            </button>
          </div>
        )}
      </div>

      {(pos.entry_outlook ||
        tier.kind === "long" ||
        tier.kind === "scalp" ||
        (pos.auto_quantity > 0 && !pos.excluded_from_auto)) && (
        <p className="entry-outlook-line dim">
          <strong>진입 유형:</strong>{" "}
          {pos.entry_outlook ||
            (tier.kind === "scalp"
              ? "AI 단타 자동"
              : tier.kind === "long"
                ? "AI 롱 자동"
                : pos.auto_quantity > 0
                  ? "AI 자동 (롱·현물 매수)"
                  : "")}
        </p>
      )}
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
              ? " — AI 자동매수만 제외 (손익절은 아래 설정 따름)"
              : pos.auto_quantity > 0
                ? " — 해제(기본): AI 자동매수 포함"
                : " — 수동 보유"}
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
  tradesSyncError,
  tradesDisplayCount,
  tradesOrdersFetched,
  upbitSnapshot,
  onManualBuy,
  onManualSell,
  onSellAll,
  onSelectChart,
  onExclude,
  onExitPlan,
  onMigrateExits,
  stopLossPct,
  takeProfitPct,
  minBuyKrw = 10_000,
  onSaveMinBuyKrw,
  savingMinBuy,
  busy,
}: Props) {
  const minBuy = getMinBuyKrw({ min_buy_krw: minBuyKrw });
  const [buySymbol, setBuySymbol] = useState("BTCUSDT");
  const [buyAmount, setBuyAmount] = useState(500_000);
  const running = isRunning(botStatus);
  const canTrade = botStatus !== "stopping";
  const maxKrw = maxBuyKrw(portfolio.cash_krw, minBuy);

  useEffect(() => {
    setBuyAmount((prev) => Math.max(minBuy, Math.min(prev, maxKrw)));
  }, [maxKrw, minBuy]);

  return (
    <div className="funds-tab funds-tab-body">
      {onSaveMinBuyKrw && (
        <MinBuyKrwPanel
          value={minBuy}
          saving={savingMinBuy}
          onSave={onSaveMinBuyKrw}
        />
      )}
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
              minBuyKrw={minBuy}
            />
            <button
              type="button"
              className="btn-primary buy-submit-btn"
              disabled={
                busy ||
                buyAmount < minBuy ||
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
          {portfolio.positions.length > 0 && onMigrateExits && (
            <button
              type="button"
              className="btn-ghost btn-sm"
              disabled={busy}
              onClick={() => onMigrateExits()}
            >
              진입 유형별 손익절 재적용
            </button>
          )}
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
              onExitPlan={(plan) => onExitPlan(p.symbol, plan)}
              stopLossPct={stopLossPct}
              takeProfitPct={takeProfitPct}
            />
          ))
        )}
      </section>

      <section className="funds-trades">
        <h3>
          매매 내역
          {tradeMode === "live" && (tradesDisplayCount ?? trades.length) > 0 && (
            <span className="funds-trades-meta">
              {" "}
              · 표시 {tradesDisplayCount ?? trades.length}건
              {tradesOrdersFetched && tradesOrdersFetched > (tradesDisplayCount ?? 0)
                ? ` (업비트 체결 ${tradesOrdersFetched}건 중)`
                : ""}
            </span>
          )}
        </h3>
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
                <th>진입</th>
                <th>사유</th>
              </tr>
            </thead>
            <tbody>
              {trades.length === 0 ? (
                <tr>
                  <td colSpan={8} className="empty-cell">
                    {tradesSyncError
                      ? `체결 내역 없음 — ${tradesSyncError}`
                      : tradeMode === "live"
                        ? "업비트 체결 조회 중… (API 키에 주문·거래 조회 권한 필요)"
                        : "체결 내역 없음"}
                  </td>
                </tr>
              ) : (
                trades
                  .slice()
                  .reverse()
                  .map((t, i) => {
                    const qty = tradeQuantity(t);
                    const amt = tradeAmountKrw(t);
                    const pxKrw = tradeUnitPriceKrw(t);
                    const pxText =
                      pxKrw > 0
                        ? `${fmtKrw(pxKrw)}원`
                        : t.price > 0
                          ? `$${fmtUsd(t.price)}`
                          : "—";
                    return (
                      <tr
                        key={`${t.ts}-${i}`}
                        className={t.side === "BUY" ? "buy" : "sell"}
                      >
                        <td>{fmtTime(t.ts)}</td>
                        <td>{t.display}</td>
                        <td>{t.side === "BUY" ? "매수" : "매도"}</td>
                        <td>{pxText}</td>
                        <td>{fmtQty(qty)}</td>
                        <td>{amt > 0 ? `${fmtKrw(amt)}원` : "—"}</td>
                        <td className="trade-entry-mode">
                          {t.side === "BUY" && t.entry_mode ? t.entry_mode : "—"}
                        </td>
                        <td>{t.reason}</td>
                      </tr>
                    );
                  })
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

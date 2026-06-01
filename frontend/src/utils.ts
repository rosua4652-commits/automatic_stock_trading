import type {
  AppConfig,
  CoinCandidate,
  InvestmentRecommendation,
  Portfolio,
  Position,
  StatusPayload,
  TabQuote,
} from "./types";

export function fmtKrw(n: number) {
  const rounded = Math.round(n);
  if (rounded === 0 && Math.abs(n) >= 0.01) {
    return n.toLocaleString("ko-KR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }
  return new Intl.NumberFormat("ko-KR").format(rounded);
}

export function fmtQty(q: number) {
  if (!Number.isFinite(q) || q <= 0) return "—";
  if (q >= 1) return q.toLocaleString("ko-KR", { maximumFractionDigits: 4 });
  return q.toLocaleString("ko-KR", { maximumFractionDigits: 8 });
}

export function tradeUnitPriceKrw(t: {
  price_krw?: number;
  price: number;
  quantity: number;
  amount_krw: number;
}) {
  if (t.price_krw && t.price_krw > 0) return t.price_krw;
  if (t.quantity > 1e-12 && t.amount_krw > 0) return t.amount_krw / t.quantity;
  if (t.price > 0) return t.price * 1350;
  return 0;
}

export function tradeAmountKrw(t: {
  amount_krw: number;
  quantity: number;
  price_krw?: number;
  price: number;
}) {
  if (t.amount_krw > 0) return t.amount_krw;
  const px = tradeUnitPriceKrw(t);
  if (px > 0 && t.quantity > 0) return px * t.quantity;
  return 0;
}

export function tradeQuantity(t: {
  quantity: number;
  amount_krw: number;
  price_krw?: number;
  price: number;
}) {
  if (t.quantity > 1e-12) return t.quantity;
  const px = tradeUnitPriceKrw(t);
  if (px > 0 && t.amount_krw > 0) return t.amount_krw / px;
  return 0;
}

export function fmtUsd(n: number, digits = 2) {
  if (n >= 1000) return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (n >= 1) return n.toLocaleString("en-US", { maximumFractionDigits: digits });
  return n.toLocaleString("en-US", { maximumFractionDigits: 6 });
}

export function fmtPct(n: number) {
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

/** 업비트 스타일 24h 거래대금 (KRW) */
export function fmtVolumeKrw(n: number) {
  if (!Number.isFinite(n) || n <= 0) return "—";
  const jo = n / 1e12;
  if (jo >= 1) return `${jo.toLocaleString("ko-KR", { maximumFractionDigits: 1 })}조`;
  const eok = n / 1e8;
  if (eok >= 1) return `${eok.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}억`;
  const man = n / 1e4;
  if (man >= 1) return `${man.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}만`;
  return `${fmtKrw(n)}원`;
}

/** 설정 익절·손절 % (소수 둘째 자리) */
export function roundPct2(n: number) {
  return Math.round(n * 100) / 100;
}

/** 설정 익절·손절 % 표시 (최대 소수 둘째, 불필요한 0 제거) */
export function fmtPctSetting(n: number) {
  const v = roundPct2(Number.isFinite(n) ? n : 0);
  const s = v.toFixed(2).replace(/\.?0+$/, "");
  return `${s}%`;
}

export function isRunning(status: string) {
  return status === "running" || status === "stopping";
}

export function labelForSymbol(
  symbol: string,
  portfolio: Portfolio,
  candidates: CoinCandidate[]
): string {
  const pos = portfolio.positions.find((p) => p.symbol === symbol);
  if (pos) return pos.base;
  const c = candidates.find((x) => x.symbol === symbol);
  if (c) return c.base;
  return symbol.replace("USDT", "");
}

export function displayForSymbol(
  symbol: string,
  portfolio: Portfolio,
  candidates: CoinCandidate[]
): string {
  const pos = portfolio.positions.find((p) => p.symbol === symbol);
  if (pos) return pos.display;
  const c = candidates.find((x) => x.symbol === symbol);
  if (c) return c.display;
  const base = symbol.replace("USDT", "");
  return `${base} (${base})`;
}

/** 탭·목록용 진입 상태 */
export type CoinMetaBrief = {
  symbol: string;
  name_ko: string;
  base: string;
  pair_label: string;
};

/** 코인 탭 — 평단·현재가·수익률 (보유) / 현재가·24h (미보유) */
export function coinTabDisplay(
  symbol: string,
  portfolio: Portfolio,
  quote?: TabQuote
) {
  const pos = portfolio.positions.find((p) => p.symbol === symbol);
  if (pos && pos.quantity > 0) {
    return {
      held: true,
      avgKrw: Math.round(pos.cost_basis_krw / pos.quantity),
      currentKrw: Math.round(pos.current_value_krw / pos.quantity),
      pnlPct: pos.pnl_pct,
      change24h: undefined as number | undefined,
      volume24hKrw: quote?.volume_24h_krw,
    };
  }
  const px = quote?.price_krw ?? 0;
  return {
    held: false,
    avgKrw: undefined as number | undefined,
    currentKrw: px > 0 ? px : undefined,
    pnlPct: undefined as number | undefined,
    change24h: quote?.change_24h,
    volume24hKrw: quote?.volume_24h_krw,
  };
}

export function resolveCoinMeta(
  symbol: string,
  portfolio: Portfolio,
  candidates: CoinCandidate[]
): CoinMetaBrief {
  const pos = portfolio.positions.find((p) => p.symbol === symbol);
  if (pos) {
    return {
      symbol,
      name_ko: pos.name_ko,
      base: pos.base,
      pair_label: pos.pair_label,
    };
  }
  const c = candidates.find((x) => x.symbol === symbol);
  if (c) {
    return {
      symbol,
      name_ko: c.name_ko,
      base: c.base,
      pair_label: c.pair_label,
    };
  }
  const base = symbol.replace("USDT", "");
  return {
    symbol,
    name_ko: base,
    base,
    pair_label: `${base}/USDT`,
  };
}

export function matchCoinSearch(
  query: string,
  symbol: string,
  portfolio: Portfolio,
  candidates: CoinCandidate[]
): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const meta = resolveCoinMeta(symbol, portfolio, candidates);
  if (symbol.toLowerCase().includes(q)) return true;
  if (meta.base.toLowerCase().includes(q)) return true;
  if (meta.name_ko.toLowerCase().includes(q)) return true;
  if (meta.name_ko.includes(query.trim())) return true;
  const c = candidates.find((x) => x.symbol === symbol);
  if (c?.name_en?.toLowerCase().includes(q)) return true;
  return false;
}

export function entryBadge(c: CoinCandidate | undefined): {
  label: string;
  kind: "ok" | "scalp" | "hold" | "none";
} {
  if (!c) return { label: "", kind: "none" };
  if (c.entry_ok) return { label: "추천", kind: "ok" };
  if (c.entry_scalp_ok) return { label: "단타", kind: "scalp" };
  if (c.entry_detail) return { label: "보류", kind: "hold" };
  return { label: "—", kind: "none" };
}

/** WebSocket으로 bot 상태가 덮어쓰이지 않도록 (시작/중지 직후) */
export function mergeWsPayload(
  local: StatusPayload,
  incoming: StatusPayload,
  botLockVersion: number
): StatusPayload {
  const incomingVer = incoming.status_version ?? 0;
  if (incomingVer < botLockVersion) {
    return {
      ...incoming,
      bot: { ...incoming.bot, status: local.bot.status, message: local.bot.message },
    };
  }
  return incoming;
}

/** 업비트 주문 하한 (원) — 설정보다 낮출 수 없음 */
export const UPBIT_MIN_ORDER_KRW = 5_000;

/** @deprecated config.min_buy_krw 사용 */
export const MIN_BUY_KRW = UPBIT_MIN_ORDER_KRW;

/** 자동투자·승인·제안 배분에 쓰는 건당 최소 매수 금액 */
export function getAutoMinBuyKrw(config?: { min_buy_krw?: number } | null): number {
  const raw = Number(config?.min_buy_krw);
  if (!Number.isFinite(raw) || raw <= 0) return 6_000;
  return Math.max(UPBIT_MIN_ORDER_KRW, Math.round(raw / 1000) * 1000);
}

/** @alias getAutoMinBuyKrw */
export const getMinBuyKrw = getAutoMinBuyKrw;

/** 수동 지정 매수 — 업비트 주문 하한(5,000원)만 */
export function getManualMinBuyKrw(): number {
  return UPBIT_MIN_ORDER_KRW;
}

/** API·저장 설정에 min_buy_krw 없을 때 기본값 보정 */
export function normalizeAppConfig(cfg: AppConfig): AppConfig {
  return {
    ...DEFAULT_CONFIG,
    ...cfg,
    min_buy_krw: getAutoMinBuyKrw(cfg),
  };
}

/** 편도 fee% · 왕복(매수+매도) 반영 후 배분 가능 매수 원금 */
export function deployableCashKrw(cashKrw: number, feePct = 0.05) {
  const feeR = Math.max(0, feePct) / 100;
  const roundTrip = (1 + feeR) ** 2;
  return Math.max(0, (cashKrw / roundTrip) * 0.98);
}

export function roundTripFeePct(feePct = 0.05) {
  return Math.max(0, feePct) * 2;
}

export function cashRequiredForBuy(principalKrw: number, feePct = 0.05) {
  const feeR = Math.max(0, feePct) / 100;
  return principalKrw * (1 + feeR);
}

/** 제안 금액 합이 현금을 넘지 않도록 비중 재배분 */
export function balanceRecommendationAmounts(
  recs: { symbol: string; amount_krw: number; selected?: boolean }[],
  cashKrw: number,
  feePct = 0.05,
  minBuyKrw = 10_000
): Record<string, number> {
  const floor = getAutoMinBuyKrw({ min_buy_krw: minBuyKrw });
  const budget = Math.round(deployableCashKrw(cashKrw, feePct) / 1000) * 1000;
  const active = recs.filter((r) => r.selected !== false);
  if (!active.length || budget < floor) return {};

  const weights = active.map((r) => Math.max(1, r.amount_krw));
  const wsum = weights.reduce((a, b) => a + b, 0);
  let amounts = active.map((r, i) =>
    Math.max(floor, Math.round((budget * weights[i]) / wsum / 1000) * 1000)
  );

  const trim = () => {
    while (amounts.reduce((a, b) => a + b, 0) > budget && amounts.length > 1) {
      amounts.pop();
      const ws = weights.slice(0, amounts.length);
      const s = ws.reduce((a, b) => a + b, 0) || 1;
      amounts = ws.map((w) =>
        Math.max(floor, Math.round((budget * w) / s / 1000) * 1000)
      );
    }
    let total = amounts.reduce((a, b) => a + b, 0);
    while (total > budget && amounts.length) {
      const over = total - budget;
      let i = amounts.indexOf(Math.max(...amounts));
      const cut = Math.min(over, amounts[i] - floor);
      if (cut < 1000) {
        if (amounts.length > 1) {
          amounts.splice(i, 1);
        } else {
          amounts[0] = Math.min(amounts[0], budget);
          break;
        }
      } else {
        amounts[i] = amounts[i] - cut;
      }
      total = amounts.reduce((a, b) => a + b, 0);
    }
  };
  trim();

  const out: Record<string, number> = {};
  active.slice(0, amounts.length).forEach((r, i) => {
    if (amounts[i] >= floor) out[r.symbol] = amounts[i];
  });
  return out;
}

/** 보유 포지션 익절·손절 (USDT 가격 + 원화 예상 손익) */
export function positionTpSl(pos: Position) {
  const { avg_price, cost_basis_krw, stop_loss, take_profit } = pos;
  const hasLevels = stop_loss > 0 && take_profit > 0;
  if (!hasLevels || avg_price <= 0) {
    return { hasLevels: false, stop_loss: 0, take_profit: 0, stop_loss_krw: 0, take_profit_krw: 0 };
  }
  const stop_loss_krw = Math.round(
    Math.max(0, ((avg_price - stop_loss) / avg_price) * cost_basis_krw)
  );
  const take_profit_krw = Math.round(
    Math.max(0, ((take_profit - avg_price) / avg_price) * cost_basis_krw)
  );
  return {
    hasLevels: true,
    stop_loss,
    take_profit,
    stop_loss_krw,
    take_profit_krw,
  };
}

/** 미보유 시 AI 제안·설정 기준 익절·손절 */
export function recommendationTpSl(
  rec: InvestmentRecommendation | null | undefined,
  priceUsdt: number,
  amountKrw: number,
  stopLossPct: number,
  takeProfitPct: number,
  usdtKrw = 1400
) {
  if (rec?.stop_loss_krw && rec?.take_profit_krw) {
    return {
      hasLevels: true,
      stop_loss: rec.stop_loss_price_usdt ?? 0,
      take_profit: rec.take_profit_price_usdt ?? 0,
      stop_loss_krw: rec.stop_loss_krw,
      take_profit_krw: rec.take_profit_krw,
      fromAi: true,
    };
  }
  if (priceUsdt <= 0 || amountKrw < UPBIT_MIN_ORDER_KRW) {
    return { hasLevels: false, stop_loss: 0, take_profit: 0, stop_loss_krw: 0, take_profit_krw: 0, fromAi: false };
  }
  const plan = computeTradePlan(amountKrw, priceUsdt, usdtKrw, stopLossPct, takeProfitPct);
  return {
    hasLevels: true,
    stop_loss: plan.stop_loss_price_usdt,
    take_profit: plan.take_profit_price_usdt,
    stop_loss_krw: plan.stop_loss_krw,
    take_profit_krw: plan.take_profit_krw,
    fromAi: false,
  };
}

/** 매수 금액 기준 예상 수량·손절/익절 (원화) */
export function computeTradePlan(
  amountKrw: number,
  priceUsdt: number,
  usdtKrw: number,
  stopLossPct: number,
  takeProfitPct: number,
  feePct = 0.05
) {
  if (priceUsdt <= 0 || usdtKrw <= 0 || amountKrw <= 0) {
    return {
      quantity_est: 0,
      stop_loss_price_usdt: 0,
      take_profit_price_usdt: 0,
      stop_loss_krw: 0,
      take_profit_krw: 0,
    };
  }
  const slR = stopLossPct / 100;
  const tpR = takeProfitPct / 100;
  const slPrice = priceUsdt * (1 - slR);
  const tpPrice = priceUsdt * (1 + tpR);
  const qty = amountKrw / (priceUsdt * usdtKrw);
  let slKrw = Math.max(0, (priceUsdt - slPrice) * qty * usdtKrw);
  let tpKrw = Math.max(0, (tpPrice - priceUsdt) * qty * usdtKrw);
  const feesRt = amountKrw * (Math.max(0, feePct) / 100) * 2;
  slKrw = Math.max(0, slKrw + feesRt);
  tpKrw = Math.max(0, tpKrw - feesRt);
  return {
    quantity_est: Math.round(qty * 1e6) / 1e6,
    stop_loss_price_usdt: slPrice,
    take_profit_price_usdt: tpPrice,
    stop_loss_krw: Math.round(slKrw),
    take_profit_krw: Math.round(tpKrw),
  };
}

/** 차트 자동 갱신 주기 (초봉은 1초마다) */
export function chartRefreshMs(interval: string): number {
  if (interval === "1s") return 3000;
  if (interval === "1m") return 8000;
  return 30000;
}

/** 평단 대비 손절·익절 가격의 % */
export function pctFromAvg(avg: number, level: number): number | null {
  if (avg <= 0 || level <= 0) return null;
  return ((level - avg) / avg) * 100;
}

/** 손절 % (평단 대비 하락 폭, 양수로 표시 e.g. 3) */
export function lossPctFromAvg(avg: number, stopLoss: number, fallback: number): number {
  if (avg <= 0 || stopLoss <= 0) return fallback;
  return Math.max(0.01, ((avg - stopLoss) / avg) * 100);
}

/** 익절 % (평단 대비 상승 폭, 양수로 표시 e.g. 5) */
export function gainPctFromAvg(avg: number, takeProfit: number, fallback: number): number {
  if (avg <= 0 || takeProfit <= 0) return fallback;
  return Math.max(0.01, ((takeProfit - avg) / avg) * 100);
}

/** 평단·% → 손절/익절 USDT 가격 */
export function pricesFromExitPct(
  avg: number,
  stopLossPct: number,
  takeProfitPct: number
): { stop_loss: number; take_profit: number } {
  const sl = Math.max(0.01, stopLossPct);
  const tp = Math.max(0.01, takeProfitPct);
  return {
    stop_loss: avg * (1 - sl / 100),
    take_profit: avg * (1 + tp / 100),
  };
}

/** 보유 카드 — 롱/단타/AI 구분 (entry_outlook · 진입 근거) */
export function resolveEntryTier(pos: {
  entry_outlook?: string;
  entry_reason?: string;
  auto_quantity?: number;
  manual_quantity?: number;
}): { kind: "scalp" | "long" | "ai" | "manual" | null; label: string } {
  const text = `${pos.entry_outlook || ""} ${pos.entry_reason || ""}`.toLowerCase();
  if (text.includes("단타") || text.includes("scalp")) {
    return { kind: "scalp", label: "단타" };
  }
  if (text.includes("롱") || text.includes("long")) {
    return { kind: "long", label: "롱" };
  }
  if ((pos.auto_quantity ?? 0) > 1e-10) return { kind: "ai", label: "AI" };
  if ((pos.manual_quantity ?? 0) > 1e-10) return { kind: "manual", label: "수동" };
  return { kind: null, label: "" };
}

export const DEFAULT_CONFIG: AppConfig = {
  trade_mode: "paper" as const,
  target_profit_krw: 2_000_000,
  initial_balance_krw: 10_000_000,
  max_positions: 6,
  max_position_weight_pct: 12,
  trade_hours_enabled: true,
  trade_start_hour_kst: 8,
  trade_end_hour_kst: 23,
  paper_days_before_live_auto: 3,
  stop_loss_pct: 3,
  take_profit_pct: 1.2,
  trading_fee_pct: 0.05,
  scan_interval_sec: 30,
  min_buy_score: 28,
  min_buy_krw: 6_000,
  min_entry_score: 38,
  max_auto_buys_per_scan: 2,
  paper_max_auto_buys_per_scan: 4,
  paper_auto_deploy_pct: 40,
  daily_loss_limit_pct: 5,
  allow_live_auto_invest: false,
  ai_auto_settings: true,
  flash_guard_enabled: true,
  flash_drop_from_peak_pct: 2.8,
  flash_tick_drop_pct: 1.2,
  flash_candle_1m_drop_pct: 3.5,
  flash_window_sec: 90,
  flash_block_minutes: 45,
  flash_hard_stop_pct: 0,
  exchange: "upbit",
  api_access_key: "",
  api_secret_key: "",
  binance_api_key: "",
  binance_api_secret: "",
  use_testnet: false,
};

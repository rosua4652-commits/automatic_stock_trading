export type BotStatus = "stopped" | "running" | "stopping";
export type TradeMode = "paper" | "live";
export type MainView = "chart" | "funds";

export interface AppConfig {
  trade_mode: TradeMode;
  target_profit_krw: number;
  initial_balance_krw: number;
  max_positions: number;
  stop_loss_pct: number;
  take_profit_pct: number;
  scan_interval_sec: number;
  min_buy_score: number;
  min_entry_score: number;
  binance_api_key: string;
  binance_api_secret: string;
}

export interface CoinMeta {
  symbol: string;
  base: string;
  quote: string;
  name_ko: string;
  name_en: string;
  pair_label: string;
  display: string;
}

export interface Position {
  symbol: string;
  base: string;
  name_ko: string;
  name_en: string;
  pair_label: string;
  display: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  stop_loss: number;
  take_profit: number;
  pnl_pct: number;
  cost_basis_krw: number;
  current_value_krw: number;
  pnl_krw: number;
  weight_pct: number;
  entry_reason: string;
  entry_score: number;
  entry_outlook: string;
  auto_managed: boolean;
  score: number;
}

export interface Portfolio {
  cash_krw: number;
  total_value_krw: number;
  invested_krw: number;
  principal_krw: number;
  unrealized_pnl_krw: number;
  realized_pnl_krw: number;
  profit_toward_target_krw: number;
  target_profit_krw: number;
  progress_pct: number;
  positions: Position[];
}

export interface CoinCandidate {
  symbol: string;
  base: string;
  name_ko: string;
  name_en: string;
  pair_label: string;
  display: string;
  score: number;
  trend: string;
  rsi: number;
  change_24h: number;
  reason: string;
  entry_score: number;
  entry_ok: boolean;
  entry_outlook: string;
}

export interface TradeEvent {
  ts: number;
  symbol: string;
  base: string;
  display: string;
  side: string;
  price: number;
  quantity: number;
  amount_krw: number;
  amount_usdt: number;
  reason: string;
}

export interface CoinView {
  meta: CoinMeta;
  price_usdt: number;
  change_24h: number;
  in_portfolio: boolean;
  position: Position | null;
  candidate: CoinCandidate | null;
}

export interface BotState {
  status: BotStatus;
  view_symbol: string;
  message: string;
  candidates: CoinCandidate[];
  recent_trades: TradeEvent[];
  manual_mode: boolean;
}

export interface StatusPayload {
  bot: BotState;
  portfolio: Portfolio;
  config: AppConfig;
  view: CoinView;
  tabs: string[];
  status_version?: number;
  all_trades?: TradeEvent[];
  ok?: boolean;
  message?: string;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ChartResponse {
  symbol: string;
  interval: string;
  candles: Candle[];
}

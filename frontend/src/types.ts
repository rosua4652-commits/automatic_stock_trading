export type BotStatus = "stopped" | "running" | "stopping";
export type TradeMode = "paper" | "live";
export type MainView = "alerts" | "chart" | "funds";

export interface TabQuote {
  price_usdt: number;
  price_krw: number;
  change_24h: number;
}

export interface AppConfig {
  trade_mode: TradeMode;
  target_profit_krw: number;
  initial_balance_krw: number;
  max_positions: number;
  stop_loss_pct: number;
  take_profit_pct: number;
  trading_fee_pct?: number;
  scan_interval_sec: number;
  min_buy_score: number;
  min_entry_score: number;
  exchange?: string;
  api_access_key?: string;
  api_secret_key?: string;
  api_access_key_masked?: string;
  api_secret_key_masked?: string;
  has_saved_keys?: boolean;
  binance_api_key: string;
  binance_api_secret: string;
  use_testnet: boolean;
}

export interface CredentialsTestResult {
  ok: boolean;
  message?: string;
  exchange?: string;
  krw_balance?: number;
  coin_count?: number;
  accounts?: number;
  outbound_ip?: string;
  outbound_ipv4_stack?: string;
  access_key_hint?: string;
  key_source?: string;
  hint?: string;
  upbit_error_name?: string | null;
  upbit_error_message?: string | null;
  raw_body?: string;
}

export interface AccountLink {
  linked: boolean;
  mode: string;
  message: string;
  last_sync?: number;
  total_assets_krw?: number;
  cash_krw?: number;
  exchange?: string;
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
  auto_quantity: number;
  manual_quantity: number;
  avg_price: number;
  auto_avg_price?: number;
  current_price: number;
  stop_loss: number;
  take_profit: number;
  pnl_pct: number;
  auto_pnl_pct?: number;
  cost_basis_krw: number;
  current_value_krw: number;
  pnl_krw: number;
  weight_pct: number;
  entry_reason: string;
  entry_score: number;
  entry_outlook: string;
  excluded_from_auto: boolean;
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
  entry_scalp_ok?: boolean;
  entry_outlook: string;
  entry_detail?: string;
  entry_pattern?: string;
  entry_reasons?: string[];
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

export interface InvestmentRecommendation {
  symbol: string;
  base: string;
  name_ko: string;
  display: string;
  pair_label: string;
  market_score: number;
  entry_score: number;
  weight_pct: number;
  amount_krw: number;
  price_usdt?: number;
  quantity_est?: number;
  stop_loss_price_usdt?: number;
  take_profit_price_usdt?: number;
  stop_loss_krw?: number;
  take_profit_krw?: number;
  entry_tier?: string;
  entry_detail: string;
  change_24h: number;
  trend: string;
  selected?: boolean;
}

export interface BotState {
  status: BotStatus;
  view_symbol: string;
  message: string;
  candidates: CoinCandidate[];
  recommendations?: InvestmentRecommendation[];
  recent_trades: TradeEvent[];
  manual_mode: boolean;
}

export interface StatusPayload {
  bot: BotState;
  portfolio: Portfolio;
  config: AppConfig;
  view: CoinView;
  tabs: string[];
  tab_quotes?: Record<string, TabQuote>;
  account_link?: AccountLink;
  status_version?: number;
  aidi_build?: string;
  network?: {
    outbound_ip?: string;
    outbound_ipv4_stack?: string;
    register_on_upbit?: string;
    saved_access_key?: string;
  };
  all_trades?: TradeEvent[];
  ok?: boolean;
  message?: string;
  switch_message?: string;
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

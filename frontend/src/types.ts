export type BotStatus = "stopped" | "running" | "stopping";
export type TradeMode = "paper" | "live";
export type MainView = "alerts" | "chart" | "funds";

export interface TabQuote {
  price_usdt: number;
  price_krw: number;
  change_24h: number;
  /** 업비트 24h 누적 거래대금 (KRW) */
  volume_24h_krw?: number;
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
  custom_sl_tp?: boolean;
  custom_stop_loss_pct?: number;
  custom_take_profit_pct?: number;
  score: number;
  /** 실거래: 업비트 API 기준 필드 */
  data_source?: string;
  exchange_quantity?: number;
  avg_buy_price_krw?: number;
  current_price_krw?: number;
  valuation_krw?: number;
}

export interface UpbitHoldingRow {
  symbol: string;
  market: string;
  currency: string;
  quantity: number;
  avg_buy_price_krw: number;
  current_price_krw: number;
  valuation_krw: number;
  cost_basis_krw: number;
}

export interface UpbitAccountSnapshot {
  source: string;
  synced_at: number;
  krw_balance: number;
  coin_valuation_krw: number;
  total_assets_krw: number;
  invested_principal_krw: number;
  holdings: UpbitHoldingRow[];
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
  data_source?: string;
  upbit_synced_at?: number;
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
  price_krw?: number;
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

export interface DirectionSignalItem {
  signal_id: string;
  symbol: string;
  base: string;
  name_ko: string;
  display: string;
  side: string;
  score: number;
  price_usdt: number;
  rsi: number;
  trend: string;
  outlook: string;
  detail: string;
  reasons: string[];
  scanned_at: number;
}

export interface BacktestStatus {
  running: boolean;
  last_run: number;
  message: string;
  symbols_tested: number;
  win_rate_pct: number;
  avg_return_pct: number;
  trades_simulated: number;
}

export interface BotState {
  status: BotStatus;
  view_symbol: string;
  message: string;
  candidates: CoinCandidate[];
  recommendations?: InvestmentRecommendation[];
  long_signals?: DirectionSignalItem[];
  short_signals?: DirectionSignalItem[];
  direction_scan_message?: string;
  backtest?: BacktestStatus;
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
  upbit_snapshot?: UpbitAccountSnapshot;
  status_version?: number;
  aidi_build?: string;
  aidi_capabilities?: {
    exit_plan_pct?: boolean;
    manual_sl_tp?: boolean;
    small_sell_retry?: boolean;
  };
  network?: {
    outbound_ip?: string;
    outbound_ipv4_stack?: string;
    register_on_upbit?: string;
    saved_access_key?: string;
  };
  all_trades?: TradeEvent[];
  trades_sync_error?: string;
  trades_display_count?: number;
  trades_orders_fetched?: number;
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
  stale?: boolean;
  chart_error?: string;
}

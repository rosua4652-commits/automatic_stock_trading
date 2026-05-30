export interface Position {
  symbol: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  stop_loss: number;
  take_profit: number;
  pnl_pct: number;
  value: number;
}

export interface Portfolio {
  cash_krw: number;
  total_value_krw: number;
  invested_krw: number;
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
  score: number;
  trend: string;
  rsi: number;
  change_24h: number;
  reason: string;
}

export interface TradeEvent {
  ts: number;
  symbol: string;
  side: string;
  price: number;
  quantity: number;
  reason: string;
}

export interface BotState {
  status: "stopped" | "running";
  selected_symbol: string;
  message: string;
  candidates: CoinCandidate[];
  recent_trades: TradeEvent[];
}

export interface AppConfig {
  target_profit_krw: number;
}

export interface StatusPayload {
  bot: BotState;
  portfolio: Portfolio;
  config: AppConfig;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

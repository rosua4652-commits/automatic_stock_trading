from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    min_buy_krw: float = 10_000.0  # env fallback; AppConfig.min_buy_krw 우선
    initial_balance_krw: float = 10_000_000.0
    binance_api: str = "https://api.binance.com/api/v3"
    scan_interval_sec: int = 45
    max_positions: int = 6
    # 스캔·탭 최소 24h 거래대금 (USDT 환산)
    min_quote_volume_usdt: float = 400_000.0
    # 자동 단타: 유동성·변동성 하한
    scalp_min_quote_volume_usdt: float = 2_000_000.0
    scalp_min_abs_change_24h_pct: float = 2.0
    min_candles: int = 120
    scan_kline_min: int = 50
    tab_symbol_limit: int = 200
    scan_candidate_limit: int = 120
    default_stop_loss_pct: float = 0.06
    default_take_profit_pct: float = 0.12
    trailing_activate_pct: float = 0.05
    trailing_distance_pct: float = 0.03

    class Config:
        env_prefix = "AIDI_"


settings = Settings()

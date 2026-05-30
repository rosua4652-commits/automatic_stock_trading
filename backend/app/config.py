from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    initial_balance_krw: float = 10_000_000.0
    binance_api: str = "https://api.binance.com/api/v3"
    scan_interval_sec: int = 45
    max_positions: int = 6
    min_quote_volume_usdt: float = 5_000_000.0
    min_candles: int = 120
    default_stop_loss_pct: float = 0.06
    default_take_profit_pct: float = 0.12
    trailing_activate_pct: float = 0.05
    trailing_distance_pct: float = 0.03

    class Config:
        env_prefix = "AIDI_"


settings = Settings()

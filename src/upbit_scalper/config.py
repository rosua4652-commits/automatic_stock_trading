from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Load simple KEY=VALUE pairs without overriding existing environment."""
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return float(raw)


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class UpbitCredentials:
    access_key: str
    secret_key: str

    @property
    def is_configured(self) -> bool:
        return bool(self.access_key and self.secret_key)


@dataclass(frozen=True)
class RiskSettings:
    total_budget_krw: float = 50_000
    max_position_krw: float = 10_000
    min_position_krw: float = 5_000
    max_open_positions: int = 1
    daily_loss_limit_krw: float = 1_500
    stop_after_consecutive_losses: int = 3
    take_profit_pct: float = 1.2
    stop_loss_pct: float = 0.7
    trailing_stop_pct: float = 0.5
    taker_fee_pct: float = 0.05
    slippage_pct: float = 0.08
    min_expected_net_profit_pct: float = 0.5
    btc_crash_5m_pct: float = -1.2

    @property
    def round_trip_cost_pct(self) -> float:
        return (self.taker_fee_pct * 2) + (self.slippage_pct * 2)


@dataclass(frozen=True)
class AppConfig:
    credentials: UpbitCredentials
    risk: RiskSettings
    trading_mode: str
    live_trading_enabled: bool
    quote_currency: str
    scan_top_markets: int
    min_24h_trade_price_krw: float
    ai_enabled: bool
    cursor_api_key: str
    ai_base_url: str
    ai_model: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv()
        return cls(
            credentials=UpbitCredentials(
                access_key=os.getenv("UPBIT_ACCESS_KEY", ""),
                secret_key=os.getenv("UPBIT_SECRET_KEY", ""),
            ),
            risk=RiskSettings(
                total_budget_krw=env_float("TOTAL_BUDGET_KRW", 50_000),
                max_position_krw=env_float("MAX_POSITION_KRW", 10_000),
                min_position_krw=env_float("MIN_POSITION_KRW", 5_000),
                max_open_positions=env_int("MAX_OPEN_POSITIONS", 1),
                daily_loss_limit_krw=env_float("DAILY_LOSS_LIMIT_KRW", 1_500),
                stop_after_consecutive_losses=env_int("STOP_AFTER_CONSECUTIVE_LOSSES", 3),
                take_profit_pct=env_float("TAKE_PROFIT_PCT", 1.2),
                stop_loss_pct=env_float("STOP_LOSS_PCT", 0.7),
                trailing_stop_pct=env_float("TRAILING_STOP_PCT", 0.5),
                taker_fee_pct=env_float("TAKER_FEE_PCT", 0.05),
                slippage_pct=env_float("SLIPPAGE_PCT", 0.08),
                min_expected_net_profit_pct=env_float("MIN_EXPECTED_NET_PROFIT_PCT", 0.5),
                btc_crash_5m_pct=env_float("BTC_CRASH_5M_PCT", -1.2),
            ),
            trading_mode=os.getenv("TRADING_MODE", "paper").strip().lower(),
            live_trading_enabled=env_bool("LIVE_TRADING_ENABLED", False),
            quote_currency=os.getenv("QUOTE_CURRENCY", "KRW").strip().upper(),
            scan_top_markets=env_int("SCAN_TOP_MARKETS", 30),
            min_24h_trade_price_krw=env_float("MIN_24H_TRADE_PRICE_KRW", 1_000_000_000),
            ai_enabled=env_bool("AI_ENABLED", False),
            cursor_api_key=os.getenv("CURSOR_API_KEY", ""),
            ai_base_url=os.getenv("AI_BASE_URL", "https://api.cursor.com/v1/chat/completions"),
            ai_model=os.getenv("AI_MODEL", "gpt-4o-mini"),
        )

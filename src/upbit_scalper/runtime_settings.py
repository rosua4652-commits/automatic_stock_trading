from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from .config import AppConfig, RiskSettings


class RuntimeSettingsStore:
    """Persist non-secret runtime settings controlled by the dashboard."""

    BOOL_FIELDS = {"ai_enabled"}
    INT_FIELDS = {
        "scan_top_markets",
        "max_open_positions",
        "stop_after_consecutive_losses",
        "bot_interval_seconds",
    }
    FLOAT_FIELDS = {
        "total_budget_krw",
        "max_position_krw",
        "min_position_krw",
        "daily_loss_limit_krw",
        "take_profit_pct",
        "stop_loss_pct",
        "trailing_stop_pct",
        "taker_fee_pct",
        "slippage_pct",
        "min_expected_net_profit_pct",
        "btc_crash_5m_pct",
        "min_24h_trade_price_krw",
    }
    STRING_FIELDS = {"trading_mode", "ai_model"}
    ALL_FIELDS = BOOL_FIELDS | INT_FIELDS | FLOAT_FIELDS | STRING_FIELDS

    RISK_FIELDS = {
        "total_budget_krw",
        "max_position_krw",
        "min_position_krw",
        "max_open_positions",
        "daily_loss_limit_krw",
        "stop_after_consecutive_losses",
        "take_profit_pct",
        "stop_loss_pct",
        "trailing_stop_pct",
        "taker_fee_pct",
        "slippage_pct",
        "min_expected_net_profit_pct",
        "btc_crash_5m_pct",
    }

    def __init__(self, path: str = "data/runtime_settings.json") -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return self.sanitize(data)

    def save(self, raw_settings: dict[str, Any]) -> dict[str, Any]:
        current = self.load()
        current.update(self.sanitize(raw_settings))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        return current

    def apply(self, config: AppConfig) -> AppConfig:
        settings = self.load()
        if not settings:
            return config

        risk_data = asdict(config.risk)
        app_updates: dict[str, Any] = {}
        for key, value in settings.items():
            if key in self.RISK_FIELDS:
                risk_data[key] = value
            elif key in {"trading_mode", "scan_top_markets", "min_24h_trade_price_krw", "ai_enabled", "ai_model"}:
                app_updates[key] = value

        if "trading_mode" in app_updates:
            app_updates["trading_mode"] = str(app_updates["trading_mode"]).lower()
        if "ai_model" in app_updates:
            app_updates["ai_model"] = str(app_updates["ai_model"])

        return replace(config, risk=RiskSettings(**risk_data), **app_updates)

    def public_settings(self, config: AppConfig, interval_seconds: int) -> dict[str, Any]:
        return {
            "trading_mode": config.trading_mode,
            "ai_enabled": config.ai_enabled,
            "ai_model": config.ai_model,
            "scan_top_markets": config.scan_top_markets,
            "min_24h_trade_price_krw": config.min_24h_trade_price_krw,
            "bot_interval_seconds": interval_seconds,
            **asdict(config.risk),
            "live_trading_env_enabled": config.live_trading_enabled,
            "has_upbit_keys": config.credentials.is_configured,
            "has_cursor_api_key": bool(config.cursor_api_key),
        }

    def sanitize(self, raw_settings: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in raw_settings.items():
            if key not in self.ALL_FIELDS:
                continue
            if key in self.BOOL_FIELDS:
                sanitized[key] = _to_bool(value)
            elif key in self.INT_FIELDS:
                sanitized[key] = max(1, int(float(value)))
            elif key in self.FLOAT_FIELDS:
                sanitized[key] = float(value)
            elif key == "trading_mode":
                normalized = str(value).lower()
                if normalized in {"paper", "live"}:
                    sanitized[key] = normalized
            elif key == "ai_model":
                sanitized[key] = str(value).strip()
        return sanitized


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

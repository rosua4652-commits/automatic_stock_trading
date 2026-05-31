"""Safe numeric coercion (JSON·학습 상태 오염 방지)."""

from __future__ import annotations

from typing import Any


def as_float(value: Any, default: float = 0.0) -> float:
    """dict/str/숫자 → float. 잘못된 타입은 default."""
    if value is None:
        return default
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        v = float(value)
        if v != v:  # NaN
            return default
        return v
    if isinstance(value, dict):
        for key in (
            "take_profit_pct",
            "stop_loss_pct",
            "tp",
            "sl",
            "pct",
            "value",
        ):
            if key in value:
                return as_float(value[key], default)
        return default
    if isinstance(value, str):
        s = value.strip().replace("%", "")
        if not s:
            return default
        try:
            return float(s)
        except ValueError:
            return default
    return default

"""Chart overlay: entry / stop-loss / take-profit for current symbol."""

from __future__ import annotations

from typing import Any

from app.models import AppConfig


def chart_trade_levels(
    symbol: str,
    config: AppConfig,
    positions: dict,
    recommendations: list,
    *,
    last_price_usdt: float = 0.0,
) -> dict[str, Any]:
    sym = symbol.upper()
    pos = positions.get(sym)
    if pos and getattr(pos, "quantity", 0) > 1e-10:
        entry = float(pos.avg_price or 0)
        sl = float(pos.stop_loss or 0)
        tp = float(pos.take_profit or 0)
        if entry > 0 and sl <= 0:
            sl_p = float(getattr(pos, "custom_stop_loss_pct", 0) or config.stop_loss_pct)
            sl = entry * (1 - sl_p / 100)
        if entry > 0 and tp <= 0:
            tp_p = float(getattr(pos, "custom_take_profit_pct", 0) or config.take_profit_pct)
            tp = entry * (1 + tp_p / 100)
        return {
            "kind": "position",
            "entry": entry if entry > 0 else None,
            "stop_loss": sl if sl > 0 else None,
            "take_profit": tp if tp > 0 else None,
            "stop_loss_pct": float(getattr(pos, "custom_stop_loss_pct", 0) or config.stop_loss_pct),
            "take_profit_pct": float(
                getattr(pos, "custom_take_profit_pct", 0) or config.take_profit_pct
            ),
            "label": "보유",
        }

    for r in recommendations:
        if (r.symbol or "").upper() != sym:
            continue
        entry = float(r.price_usdt or 0) or last_price_usdt
        sl = float(r.stop_loss_price_usdt or 0)
        tp = float(r.take_profit_price_usdt or 0)
        if entry > 0 and sl <= 0 and r.stop_loss_pct:
            sl = entry * (1 - float(r.stop_loss_pct) / 100)
        if entry > 0 and tp <= 0 and r.take_profit_pct:
            tp = entry * (1 + float(r.take_profit_pct) / 100)
        return {
            "kind": "proposal",
            "entry": entry if entry > 0 else None,
            "stop_loss": sl if sl > 0 else None,
            "take_profit": tp if tp > 0 else None,
            "stop_loss_pct": float(r.stop_loss_pct or 0),
            "take_profit_pct": float(r.take_profit_pct or 0),
            "label": str(r.sl_tp_source or "AI제안"),
        }

    px = last_price_usdt
    if px > 0:
        sl_p = float(config.stop_loss_pct)
        tp_p = float(config.take_profit_pct)
        return {
            "kind": "estimate",
            "entry": px,
            "stop_loss": px * (1 - sl_p / 100),
            "take_profit": px * (1 + tp_p / 100),
            "stop_loss_pct": sl_p,
            "take_profit_pct": tp_p,
            "label": "설정 기준(미보유)",
        }

    return {"kind": "none"}

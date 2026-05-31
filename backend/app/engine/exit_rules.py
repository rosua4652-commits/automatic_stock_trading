"""손익절 판정 (업비트 KRW 평단·시세와 UI 일치)."""

from __future__ import annotations

from app.models import AppConfig, Position


def resolve_exit_prices(
    pos: Position,
    price_usdt: float,
    usdt_krw: float,
) -> tuple[float, float]:
    """손익률 계산용 (entry, current) — 동일 단위."""
    rate = max(float(usdt_krw), 1.0)
    if getattr(pos, "data_source", "") == "upbit" and pos.avg_buy_price_krw > 0:
        entry = float(pos.avg_buy_price_krw)
        if price_usdt > 0:
            current = float(price_usdt) * rate
        elif pos.current_price_krw > 0:
            current = float(pos.current_price_krw)
        elif pos.current_price > 0:
            current = float(pos.current_price) * rate
        else:
            current = 0.0
        return entry, current

    entry = (
        pos.avg_price
        or pos.auto_avg_price
        or pos.manual_avg_price
        or pos.current_price
    )
    current = float(price_usdt) if price_usdt > 0 else float(pos.current_price)
    return float(entry), float(current)


def _level_prices_krw(pos: Position, usdt_krw: float) -> tuple[float, float]:
    rate = max(float(usdt_krw), 1.0)
    sl = float(pos.stop_loss)
    tp = float(pos.take_profit)
    if getattr(pos, "data_source", "") == "upbit" and rate > 0:
        return sl * rate, tp * rate
    return sl, tp


def custom_exit_triggered(
    pos: Position,
    price_usdt: float,
    usdt_krw: float,
    config: AppConfig,
    *,
    eps: float = 1e-9,
) -> tuple[bool, str]:
    if not pos.custom_sl_tp:
        return False, ""
    entry, current = resolve_exit_prices(pos, price_usdt, usdt_krw)
    if entry <= 0 or current <= 0:
        return False, ""

    sl_r = (pos.custom_stop_loss_pct or config.stop_loss_pct) / 100
    tp_r = (pos.custom_take_profit_pct or config.take_profit_pct) / 100
    pnl = (current - entry) / entry
    if pnl <= -sl_r + eps:
        return True, "손절"
    if pnl >= tp_r - eps:
        return True, "익절"

    sl_krw, tp_krw = _level_prices_krw(pos, usdt_krw)
    if sl_krw > 0 and current <= sl_krw * 1.0001:
        return True, "손절"
    if tp_krw > 0 and current >= tp_krw * 0.9999:
        return True, "익절"
    return False, ""


def config_exit_triggered(
    pos: Position,
    price_usdt: float,
    usdt_krw: float,
    config: AppConfig,
    *,
    eps: float = 1e-9,
) -> tuple[bool, str]:
    """수동 보유 + 설정 % 손익절."""
    entry, current = resolve_exit_prices(pos, price_usdt, usdt_krw)
    if entry <= 0 or current <= 0:
        return False, ""
    sl_r = config.stop_loss_pct / 100
    tp_r = config.take_profit_pct / 100
    pnl = (current - entry) / entry
    if pnl <= -sl_r + eps:
        return True, "손절"
    if pnl >= tp_r - eps:
        return True, "익절"
    return False, ""

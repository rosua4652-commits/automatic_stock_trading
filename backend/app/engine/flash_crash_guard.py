"""급락·순간 폭락 감지 — 익절 전이라도 즉시 손절·종목 매수 차단."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from app.config import settings as app_settings
from app.models import AppConfig, Position


@dataclass
class FlashGuardState:
    """종목별 단기 시세 링."""

    samples: deque[tuple[float, float]] = field(
        default_factory=lambda: deque(maxlen=24)
    )
    peak_price: float = 0.0
    last_kline_check: float = 0.0


def _cfg_bool(config: AppConfig, name: str, default: bool = True) -> bool:
    return bool(getattr(config, name, default))


def _cfg_float(config: AppConfig, name: str, default: float) -> float:
    return float(getattr(config, name, default) or default)


def record_price_sample(
    state: FlashGuardState,
    price: float,
    *,
    ts: float | None = None,
) -> None:
    if price <= 0:
        return
    t = ts if ts is not None else time.time()
    state.samples.append((t, price))
    cutoff = t - 180
    recent = [p for ts, p in state.samples if ts >= cutoff]
    if recent:
        state.peak_price = max(recent)


async def detect_flash_crash(
    symbol: str,
    price: float,
    pos: Position | None,
    config: AppConfig,
    state: FlashGuardState,
    *,
    fetch_1m=None,
) -> tuple[bool, str]:
    """급락 신호. True면 즉시 매도 권장."""
    if not _cfg_bool(config, "flash_guard_enabled", True):
        return False, ""
    if price <= 0:
        return False, ""

    record_price_sample(state, price)

    peak_drop_pct = _cfg_float(config, "flash_drop_from_peak_pct", 2.8)
    tick_drop_pct = _cfg_float(config, "flash_tick_drop_pct", 1.2)
    candle_drop_pct = _cfg_float(config, "flash_candle_1m_drop_pct", 3.5)
    window_sec = _cfg_float(config, "flash_window_sec", 90.0)

    peak = state.peak_price
    if peak > 0:
        from_peak = (peak - price) / peak * 100
        if from_peak >= peak_drop_pct:
            return (
                True,
                f"급락 손절 · 고점(${peak:.4f}) 대비 -{from_peak:.1f}%",
            )

    now = time.time()
    cutoff = now - window_sec
    window_prices = [p for ts, p in state.samples if ts >= cutoff]
    if len(window_prices) >= 2:
        w_peak = max(window_prices)
        if w_peak > 0:
            w_drop = (w_peak - price) / w_peak * 100
            if w_drop >= peak_drop_pct * 1.05:
                return (
                    True,
                    f"급락 손절 · {int(window_sec)}초 고점 대비 -{w_drop:.1f}%",
                )

    if len(state.samples) >= 2:
        _, p_prev = state.samples[-2]
        if p_prev > 0:
            tick_drop = (p_prev - price) / p_prev * 100
            if tick_drop >= tick_drop_pct:
                return (
                    True,
                    f"급락 손절 · 순간 -{tick_drop:.1f}% ({p_prev:.4f}→{price:.4f})",
                )

    if fetch_1m and now - state.last_kline_check > 45:
        state.last_kline_check = now
        try:
            raw = await fetch_1m(symbol.upper(), 10)
            if raw and len(raw) >= 5:
                closes = [float(r[4]) for r in raw]
                ref = max(closes[-6:-1]) if len(closes) >= 6 else max(closes[:-1])
                if ref > 0:
                    c_drop = (ref - closes[-1]) / ref * 100
                    if c_drop >= candle_drop_pct:
                        return (
                            True,
                            f"급락 손절 · 1분봉 -{c_drop:.1f}% (익절 전 차단)",
                        )
        except Exception:
            pass

    if pos is not None:
        entry = pos.auto_avg_price or pos.avg_price
        if entry > 0:
            pnl_pct = (price - entry) / entry * 100
            hard_pct = _cfg_float(
                config,
                "flash_hard_stop_pct",
                app_settings.default_stop_loss_pct * 100 * 1.5,
            )
            if pnl_pct <= -abs(hard_pct):
                return (
                    True,
                    f"급락 손절 · 평단 대비 {pnl_pct:.1f}% (긴급)",
                )

    return False, ""


def is_symbol_flash_blocked(
    block_until: dict[str, float],
    symbol: str,
) -> bool:
    sym = symbol.upper()
    until = block_until.get(sym, 0)
    return until > time.time()


def block_symbol_after_flash(
    block_until: dict[str, float],
    symbol: str,
    config: AppConfig,
) -> None:
    mins = _cfg_float(config, "flash_block_minutes", 45.0)
    block_until[symbol.upper()] = time.time() + max(5.0, mins) * 60.0

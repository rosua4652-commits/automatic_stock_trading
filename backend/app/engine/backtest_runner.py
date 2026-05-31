"""백테스트 — 상위 종목 전략 시뮬 (백그라운드 주기 실행)."""

from __future__ import annotations

import asyncio
import logging
import time

import numpy as np

from app.config import settings
from app.market.scanner import top_usdt_symbols
from app.market.upbit_data import market
from app.models import BacktestStatus

logger = logging.getLogger(__name__)

_backtest_task: asyncio.Task | None = None


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    if len(values) < period:
        return values
    alpha = 2 / (period + 1)
    out = np.empty_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


async def run_backtest_once(
    *,
    symbol_limit: int = 25,
    sl_pct: float | None = None,
    tp_pct: float | None = None,
) -> BacktestStatus:
    sl = (sl_pct if sl_pct is not None else settings.default_stop_loss_pct) / 100
    tp = (tp_pct if tp_pct is not None else settings.default_take_profit_pct) / 100

    try:
        symbols = await top_usdt_symbols(min(symbol_limit, 40))
    except Exception as e:
        return BacktestStatus(
            running=True,
            last_run=time.time(),
            message=f"종목 목록 실패: {e}",
        )

    wins = 0
    losses = 0
    rets: list[float] = []
    tested = 0

    for sym in symbols[:symbol_limit]:
        try:
            raw = await market.klines(sym, "1h", 100)
        except Exception:
            continue
        if len(raw) < 60:
            continue
        closes = np.array([float(r[4]) for r in raw], dtype=float)
        ema12 = _ema(closes, 12)
        ema26 = _ema(closes, 26)
        tested += 1

        for i in range(40, len(closes) - 5):
            if ema12[i] <= ema26[i] or closes[i] <= ema12[i]:
                continue
            entry = closes[i]
            outcome = None
            for j in range(i + 1, min(i + 30, len(closes))):
                pnl = (closes[j] - entry) / entry
                if pnl <= -sl:
                    outcome = pnl
                    break
                if pnl >= tp:
                    outcome = pnl
                    break
            if outcome is None:
                continue
            rets.append(outcome * 100)
            if outcome >= 0:
                wins += 1
            else:
                losses += 1
            break

    total = wins + losses
    win_rate = (wins / total * 100) if total else 0.0
    avg_ret = float(np.mean(rets)) if rets else 0.0
    msg = (
        f"1h 추세·손익절 {sl*100:.1f}%/{tp*100:.1f}% · "
        f"{tested}종목 · 시뮬 {total}건 · 승률 {win_rate:.1f}% · 평균 {avg_ret:+.2f}%"
    )
    return BacktestStatus(
        running=True,
        last_run=time.time(),
        message=msg,
        symbols_tested=tested,
        win_rate_pct=round(win_rate, 1),
        avg_return_pct=round(avg_ret, 2),
        trades_simulated=total,
    )


async def _backtest_loop(engine) -> None:
    while True:
        try:
            engine.bot.backtest = await run_backtest_once()
            engine._notify()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("backtest loop: %s", e)
            engine.bot.backtest = BacktestStatus(
                running=True,
                last_run=time.time(),
                message=f"백테스트 오류: {e}",
            )
        await asyncio.sleep(300)


def ensure_backtest_loop(engine) -> None:
    global _backtest_task
    if _backtest_task and not _backtest_task.done():
        return
    _backtest_task = asyncio.create_task(_backtest_loop(engine))


def stop_backtest_loop() -> None:
    global _backtest_task
    if _backtest_task and not _backtest_task.done():
        _backtest_task.cancel()
    _backtest_task = None

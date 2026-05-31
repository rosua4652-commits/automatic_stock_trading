"""백테스트 루프 — 데이터 누적·최적 손익절 → 롱/숏·투자 제안 반영."""

from __future__ import annotations

import asyncio
import logging
import time

from app.config import settings
from app.engine.backtest_optimizer import BacktestAccumulator, run_accumulator_cycle
from app.market.scanner import top_usdt_symbols
from app.models import BacktestStatus

logger = logging.getLogger(__name__)

_backtest_task: asyncio.Task | None = None


def status_from_accumulator(
    acc: BacktestAccumulator,
    *,
    batch_tested: int = 0,
    batch_updated: int = 0,
    default_sl: float = 6.0,
    default_tp: float = 12.0,
) -> BacktestStatus:
    sl, tp = acc.best_global_params(default_sl, default_tp)
    long_top = acc.top_symbols("long", 5)
    short_top = acc.top_symbols("short", 5)

    total_trades = sum(
        r.long.trades + r.short.trades for r in acc.symbols.values()
    )
    all_wins = sum(r.long.wins + r.short.wins for r in acc.symbols.values())
    win_rate = (all_wins / total_trades * 100) if total_trades else 0.0

    avgs = [
        r.long.avg_return_pct
        for r in acc.symbols.values()
        if r.long.trades > 0
    ]
    avg_ret = sum(avgs) / len(avgs) if avgs else 0.0

    long_hint = (
        f"롱 {long_top[0][0].replace('USDT', '')}({long_top[0][1].score:.0f}점)"
        if long_top
        else "롱 —"
    )
    short_hint = (
        f"숏 {short_top[0][0].replace('USDT', '')}({short_top[0][1].score:.0f}점)"
        if short_top
        else "숏 —"
    )

    msg = (
        f"누적 {acc.cycles}회 · {len(acc.symbols)}종 저장 · "
        f"이번 {batch_tested}종 분석({batch_updated}건 갱신) · "
        f"손익절 {sl:.1f}%/{tp:.1f}% · 승률 {win_rate:.1f}% · "
        f"{long_hint} · {short_hint}"
    )
    return BacktestStatus(
        running=True,
        last_run=time.time(),
        message=msg,
        symbols_tested=len(acc.symbols),
        win_rate_pct=round(win_rate, 1),
        avg_return_pct=round(avg_ret, 2),
        trades_simulated=total_trades,
        cycles=acc.cycles,
        best_sl_pct=sl,
        best_tp_pct=tp,
        symbols_in_store=len(acc.symbols),
        last_batch_updated=batch_updated,
    )


async def run_backtest_once(engine=None) -> BacktestStatus:
    default_sl = settings.default_stop_loss_pct
    default_tp = settings.default_take_profit_pct
    if engine is not None:
        default_sl = float(engine.config.stop_loss_pct or default_sl)
        default_tp = float(engine.config.take_profit_pct or default_tp)

    try:
        symbols = await top_usdt_symbols(80)
    except Exception as e:
        acc = BacktestAccumulator()
        return BacktestStatus(
            running=True,
            last_run=time.time(),
            message=f"종목 목록 실패: {e}",
            cycles=acc.cycles,
            symbols_in_store=len(acc.symbols),
        )

    acc, tested, updated = await run_accumulator_cycle(
        symbols,
        default_sl=default_sl,
        default_tp=default_tp,
        batch_size=20,
    )
    status = status_from_accumulator(
        acc,
        batch_tested=tested,
        batch_updated=updated,
        default_sl=default_sl,
        default_tp=default_tp,
    )
    if engine is not None:
        try:
            await engine.apply_backtest_insights(acc)
        except Exception as e:
            logger.warning("apply_backtest_insights: %s", e)
    return status


async def _backtest_loop(engine) -> None:
    while True:
        try:
            engine.bot.backtest = await run_backtest_once(engine)
            engine._bump_version()
            engine._notify()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("backtest loop: %s", e)
            acc = BacktestAccumulator()
            engine.bot.backtest = BacktestStatus(
                running=True,
                last_run=time.time(),
                message=f"백테스트 오류: {e}",
                cycles=acc.cycles,
                symbols_in_store=len(acc.symbols),
            )
        await asyncio.sleep(240)


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


def get_accumulator() -> BacktestAccumulator:
    return BacktestAccumulator()

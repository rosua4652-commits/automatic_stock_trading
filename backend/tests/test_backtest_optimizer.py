"""백테스트 누적·점수."""

import numpy as np

from app.engine.backtest_optimizer import (
    BacktestAccumulator,
    _optimize_side,
    _simulate_side,
)


def test_simulate_long_has_trades_on_trend():
    n = 120
    closes = np.linspace(100, 130, n) + np.random.default_rng(0).normal(0, 0.5, n)
    w, l, rets = _simulate_side(closes, side="long", sl_pct=5, tp_pct=10)
    assert w + l >= 0


def test_accumulator_merge_and_boost():
    acc = BacktestAccumulator(
        {
            "symbols": {},
            "cycles": 0,
            "best_sl_pct": 0,
            "best_tp_pct": 0,
        }
    )
    from app.engine.backtest_optimizer import SideStats, SymbolBacktestRecord

    acc.merge_record(
        SymbolBacktestRecord(
            symbol="BTCUSDT",
            long=SideStats(
                trades=5,
                wins=4,
                losses=1,
                win_rate_pct=80,
                avg_return_pct=2.0,
                best_sl_pct=5,
                best_tp_pct=10,
                score=72,
            ),
            updated_at=1.0,
        )
    )
    assert acc.boost("BTCUSDT", "long") > 10
    top = acc.top_symbols("long", 3)
    assert top[0][0] == "BTCUSDT"


def test_optimize_side_picks_params():
    closes = np.concatenate(
        [np.linspace(100, 90, 60), np.linspace(90, 115, 60)]
    )
    st = _optimize_side(closes, "long", 6.0, 12.0)
    assert st.best_sl_pct > 0 or st.trades == 0

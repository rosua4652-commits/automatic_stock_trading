"""백테스트 누적 — 롱/숏(단타)·손익절 조합 요약."""

from __future__ import annotations

from typing import Any

from app.engine.backtest_learning import load_learning_state
from app.engine.backtest_optimizer import PARAM_GRID, BacktestAccumulator
from app.engine.backtest_runner import get_accumulator


def build_backtest_report() -> dict[str, Any]:
    acc: BacktestAccumulator = get_accumulator()
    learning = load_learning_state()

    rows: list[dict[str, Any]] = []
    for sym, rec in sorted(acc.symbols.items(), key=lambda x: -max(x[1].long.score, x[1].short.score))[:40]:
        for side, label in (("long", "롱"), ("short", "단타")):
            st = rec.long if side == "long" else rec.short
            if st.trades < 1:
                continue
            rows.append(
                {
                    "symbol": sym,
                    "mode": label,
                    "trades": st.trades,
                    "win_rate_pct": st.win_rate_pct,
                    "score": st.score,
                    "best_sl_pct": st.best_sl_pct,
                    "best_tp_pct": st.best_tp_pct,
                    "avg_return_pct": st.avg_return_pct,
                }
            )

    grid_summary = [
        {"sl_pct": sl, "tp_pct": tp, "label": f"손절{sl:g}%/익절{tp:g}%"}
        for sl, tp in PARAM_GRID
    ]

    return {
        "symbols_in_store": len(acc.symbols),
        "data_maturity_pct": learning.data_maturity_pct,
        "long_min_bt_score": learning.long_min_bt_score,
        "scalp_min_bt_score": learning.scalp_min_bt_score,
        "learning_long_sl_tp": [learning.long_sl_pct, learning.long_tp_pct],
        "learning_scalp_sl_tp": [learning.scalp_sl_pct, learning.scalp_tp_pct],
        "global_best": list(acc.best_global_params(3.0, 5.0)),
        "param_grid": grid_summary,
        "top_symbols": rows[:25],
        "disclaimer": (
            "과거 캔들 백테스트 요약이며 미래 수익을 보장하지 않습니다. "
            "파라미터를 자주 바꾸면 과최적화(커브피팅) 위험이 있습니다."
        ),
    }

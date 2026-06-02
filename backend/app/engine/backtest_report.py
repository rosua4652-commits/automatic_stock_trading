"""백테스트 누적 — 롱/숏(단타)·손익절 조합 요약."""

from __future__ import annotations

import csv
import io
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

    ai_recent = getattr(learning, "ai_recent_insights", None) or []
    last_ai_msg = getattr(learning, "last_ai_message", "") or ""

    ai_lines = [
        f"{row.get('symbol', '').replace('USDT', '')} "
        f"{row.get('action')}({row.get('confidence')}%) "
        f"{(row.get('reason_ko') or '')[:40]}"
        for row in ai_recent[-8:]
        if isinstance(row, dict)
    ]

    return {
        "symbols_in_store": len(acc.symbols),
        "data_maturity_pct": learning.data_maturity_pct,
        "ai_insights": list(ai_recent)[-12:],
        "last_ai_message": last_ai_msg,
        "ai_insight_lines": ai_lines,
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


def backtest_report_csv(report: dict[str, Any] | None = None) -> str:
    """백테스트 리포트 CSV — 요약 + 종목별 상위 표."""
    data = report if report is not None else build_backtest_report()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["section", "field", "value"])
    for key in (
        "symbols_in_store",
        "data_maturity_pct",
        "long_min_bt_score",
        "scalp_min_bt_score",
        "learning_long_sl_tp",
        "learning_scalp_sl_tp",
        "global_best",
        "disclaimer",
    ):
        if key in data:
            w.writerow(["summary", key, data[key]])
    w.writerow([])
    w.writerow(["param_grid", "sl_pct", "tp_pct", "label"])
    for row in data.get("param_grid") or []:
        if isinstance(row, dict):
            w.writerow(
                [
                    "param_grid",
                    row.get("sl_pct", ""),
                    row.get("tp_pct", ""),
                    row.get("label", ""),
                ]
            )
    w.writerow([])
    w.writerow(
        [
            "top_symbols",
            "symbol",
            "mode",
            "score",
            "win_rate_pct",
            "trades",
            "best_sl_pct",
            "best_tp_pct",
            "avg_return_pct",
        ]
    )
    for row in data.get("top_symbols") or []:
        if isinstance(row, dict):
            w.writerow(
                [
                    "top_symbols",
                    row.get("symbol", ""),
                    row.get("mode", ""),
                    row.get("score", ""),
                    row.get("win_rate_pct", ""),
                    row.get("trades", ""),
                    row.get("best_sl_pct", ""),
                    row.get("best_tp_pct", ""),
                    row.get("avg_return_pct", ""),
                ]
            )
    return buf.getvalue()

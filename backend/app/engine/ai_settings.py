"""Apply backtest learning to runtime config when ai_auto_settings is on."""

from __future__ import annotations

from app.engine.backtest_learning import compute_data_maturity, load_learning_state
from app.engine.backtest_optimizer import BacktestAccumulator
from app.models import AppConfig
from app.util.numbers import as_float


def apply_ai_settings(
    config: AppConfig,
    acc: BacktestAccumulator | None,
    *,
    is_paper: bool,
) -> dict[str, float | int | str]:
    """Mutate config from BT learning; return summary of effective values."""
    if not getattr(config, "ai_auto_settings", True):
        return {}

    learn = load_learning_state()
    acc = acc or BacktestAccumulator()
    maturity = learn.data_maturity_pct or compute_data_maturity(acc)
    g_sl, g_tp = acc.best_global_params(
        config.stop_loss_pct, config.take_profit_pct
    )
    g_sl = as_float(g_sl, config.stop_loss_pct)
    g_tp = as_float(g_tp, config.take_profit_pct)
    l_sl = as_float(learn.long_sl_pct)
    l_tp = as_float(learn.long_tp_pct)

    if l_sl > 0:
        config.stop_loss_pct = l_sl
        config.take_profit_pct = l_tp or g_tp or config.take_profit_pct
    elif g_sl > 0:
        config.stop_loss_pct = g_sl
        config.take_profit_pct = g_tp
    config.stop_loss_pct = as_float(config.stop_loss_pct, 3.0)
    config.take_profit_pct = as_float(config.take_profit_pct, 5.0)

    # Scan thresholds track BT learning floors (slightly below for market pool)
    config.min_entry_score = max(
        32.0, min(55.0, learn.scalp_min_bt_score + 2.0)
    )
    config.min_buy_score = max(
        22.0, min(45.0, learn.long_min_bt_score - 12.0)
    )

    if is_paper:
        if maturity < 30:
            config.paper_max_auto_buys_per_scan = 2
            config.paper_auto_deploy_pct = min(30.0, config.paper_auto_deploy_pct)
        elif maturity < 60:
            config.paper_max_auto_buys_per_scan = 3
            config.paper_auto_deploy_pct = 35.0
        else:
            config.paper_max_auto_buys_per_scan = 4
            config.paper_auto_deploy_pct = 40.0

    return {
        "maturity_pct": round(maturity, 1),
        "stop_loss_pct": config.stop_loss_pct,
        "take_profit_pct": config.take_profit_pct,
        "min_buy_score": config.min_buy_score,
        "min_entry_score": config.min_entry_score,
        "paper_max_buys": config.paper_max_auto_buys_per_scan,
        "paper_deploy_pct": config.paper_auto_deploy_pct,
        "long_bt_floor": learn.long_min_bt_score,
        "scalp_bt_floor": learn.scalp_min_bt_score,
    }

from app.engine.backtest_learning import _clamp_auto_sl_tp, resolve_sl_tp_from_backtest
from app.engine.backtest_optimizer import BacktestAccumulator, SideStats
from app.engine.exit_strength import apply_strength_to_sl_tp
from app.models import AppConfig


def test_scalp_clamp_rejects_high_tp():
    sl, tp = _clamp_auto_sl_tp("scalp", 4.0, 11.0)
    assert tp <= 7.0
    assert sl >= tp * 1.25


def test_apply_strength_scalp_never_exceeds_seven():
    cfg = AppConfig(auto_exit_strength="strong")
    sl, tp = apply_strength_to_sl_tp(cfg, 5.0, 15.0, mode="scalp")
    assert tp <= 7.0
    assert 2.5 <= tp


def test_scalp_tier_not_moonshot_despite_news_surge():
    from types import SimpleNamespace

    from app.engine.moonshot_exit import is_moonshot_position, is_moonshot_recommendation

    rec = SimpleNamespace(
        entry_tier="scalp",
        news_surge=True,
        entry_detail="급등 +12% · 거래대금 2.0M",
    )
    assert is_moonshot_recommendation(rec) is False

    pos = SimpleNamespace(
        exit_profile="",
        entry_outlook="AI 단타 자동",
        entry_reason="차트 · 급등 +12% · 익절7%",
    )
    assert is_moonshot_position(pos) is False


def test_resolve_scalp_from_bt_symbol_capped():
    from app.engine.backtest_optimizer import SymbolBacktestRecord

    acc = BacktestAccumulator()
    sym_rec = SymbolBacktestRecord(symbol="BTCUSDT")
    sym_rec.short = SideStats(
        trades=5,
        wins=3,
        score=40.0,
        best_sl_pct=4.0,
        best_tp_pct=12.0,
    )
    acc.symbols["BTCUSDT"] = sym_rec
    sl, tp, src = resolve_sl_tp_from_backtest(
        acc,
        None,
        "BTCUSDT",
        mode="scalp",
        default_sl=3.0,
        default_tp=5.0,
        config=AppConfig(auto_exit_strength="strong"),
    )
    assert tp <= 7.0
    assert src == "BT종목"

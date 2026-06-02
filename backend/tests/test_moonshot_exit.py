from app.engine.exit_strength import apply_strength_to_sl_tp, strength_default_sl_tp
from app.engine.moonshot_exit import (
    EXIT_PROFILE_MOONSHOT,
    apply_moonshot_adaptive_exit_levels,
    is_moonshot_position,
    is_moonshot_recommendation,
    resolve_moonshot_sl_tp,
)
from app.models import AppConfig, InvestmentRecommendation, Position


def test_momentum_weak_tier():
    sl, tp, src = resolve_moonshot_sl_tp(AppConfig(), change_24h=15)
    assert sl == 5.5
    assert tp == 12.0
    assert "중기세" in src


def test_momentum_medium_tier():
    sl, tp, src = resolve_moonshot_sl_tp(AppConfig(), change_24h=25)
    assert sl == 6.0
    assert tp == 10.0
    assert "중기세" in src


def test_momentum_strong_tier():
    sl, tp, src = resolve_moonshot_sl_tp(AppConfig(), change_24h=45)
    assert sl == 7.0
    assert tp == 8.0
    assert "강기세" in src


def test_late_chase_has_lower_tp_than_early_surge():
    _, tp_early, _ = resolve_moonshot_sl_tp(AppConfig(), change_24h=10)
    _, tp_late, _ = resolve_moonshot_sl_tp(AppConfig(), change_24h=45)
    assert tp_late < tp_early


def test_moonshot_ignores_exit_strength():
    cfg = AppConfig(auto_exit_strength="weak")
    weak_sl, weak_tp = strength_default_sl_tp(cfg)
    sl, tp, _ = resolve_moonshot_sl_tp(cfg, change_24h=30)
    assert weak_sl == 2.5
    assert weak_tp == 1.2
    assert sl != weak_sl
    assert tp > weak_tp


def test_news_boost_increases_tp():
    _, tp1, _ = resolve_moonshot_sl_tp(AppConfig(), change_24h=15, news_score=0)
    _, tp2, _ = resolve_moonshot_sl_tp(AppConfig(), change_24h=15, news_score=55)
    assert tp2 > tp1


def test_caps_applied():
    cfg = AppConfig(
        moonshot_min_stop_loss_pct=4.0,
        moonshot_max_stop_loss_pct=7.0,
        moonshot_min_take_profit_pct=10.0,
        moonshot_max_take_profit_pct=20.0,
    )
    sl, tp, _ = resolve_moonshot_sl_tp(cfg, change_24h=50)
    assert sl <= 7.0
    assert tp <= 20.0


def test_fixed_when_momentum_disabled():
    cfg = AppConfig(moonshot_momentum_exit_enabled=False)
    sl, tp, src = resolve_moonshot_sl_tp(cfg, change_24h=50)
    assert sl == 6.0
    assert tp == 20.0
    assert src == "급등·설정"


def test_is_moonshot_position_by_profile():
    pos = Position(
        symbol="X",
        base="X",
        name_ko="",
        name_en="",
        pair_label="",
        display="X",
        exit_profile=EXIT_PROFILE_MOONSHOT,
    )
    assert is_moonshot_position(pos)


def test_is_moonshot_position_by_outlook():
    pos = Position(
        symbol="X",
        base="X",
        name_ko="",
        name_en="",
        pair_label="",
        display="X",
        entry_outlook="AI 급등 자동",
    )
    assert is_moonshot_position(pos)


def test_is_moonshot_recommendation():
    rec = InvestmentRecommendation(
        symbol="BTCUSDT",
        base="BTC",
        name_ko="",
        display="BTC",
        pair_label="",
        entry_tier="moonshot",
        change_24h=22,
    )
    assert is_moonshot_recommendation(rec)


def test_apply_strength_skipped_for_moonshot_mode():
    cfg = AppConfig(auto_exit_strength="weak")
    sl, tp = apply_strength_to_sl_tp(cfg, 8.0, 25.0, mode="moonshot")
    assert sl == 8.0
    assert tp == 25.0


def test_moonshot_trailing_ratchet():
    pos = Position(
        symbol="X",
        base="X",
        name_ko="",
        name_en="",
        pair_label="",
        display="X",
        stop_loss=90,
        take_profit=120,
        trailing_high=0,
    )
    apply_moonshot_adaptive_exit_levels(pos, entry=100, price=106, sl_pct=6, tp_pct=18)
    assert pos.trailing_high >= 106
    assert pos.stop_loss > 90


def test_moonshot_buy_sl_tp_not_from_weak_strength():
    cfg = AppConfig(auto_exit_strength="weak")
    sl, tp, _ = resolve_moonshot_sl_tp(cfg, change_24h=28.0, news_score=0)
    weak_sl, weak_tp = strength_default_sl_tp(cfg)
    assert (sl, tp) != (weak_sl, weak_tp)
    assert sl >= 5.0
    assert tp <= 14.0


def test_config_accepts_wide_moonshot_tp_caps():
    cfg = AppConfig(
        moonshot_min_take_profit_pct=5.0,
        moonshot_max_take_profit_pct=10.0,
    )
    _, tp, _ = resolve_moonshot_sl_tp(cfg, change_24h=15)
    assert tp == 10.0


def test_moonshot_tp_max_must_be_gte_min():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AppConfig(
            moonshot_min_take_profit_pct=20.0,
            moonshot_max_take_profit_pct=10.0,
        )

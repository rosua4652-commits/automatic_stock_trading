"""적용 시 즉시 손익절 · 업비트 KRW 평단 판정."""

from app.engine.exit_rules import (
    config_exit_triggered,
    custom_exit_triggered,
    resolve_exit_prices,
)
from app.models import AppConfig, Position


def _upbit_pos(**kw) -> Position:
    base = dict(
        symbol="ZKPUSDT",
        base="ZKP",
        name_ko="지케이패스",
        name_en="ZKP",
        pair_label="KRW-ZKP",
        display="ZKP",
        avg_price=104 / 1350,
        current_price=103 / 1350,
        avg_buy_price_krw=104,
        current_price_krw=103,
        data_source="upbit",
        manual_quantity=48.0,
        auto_quantity=0.0,
        custom_sl_tp=True,
        custom_stop_loss_pct=0.5,
        custom_take_profit_pct=5.0,
        stop_loss=(104 / 1350) * 0.995,
        take_profit=(104 / 1350) * 1.05,
    )
    base.update(kw)
    return Position(**base)


def test_resolve_exit_prices_upbit_krw():
    pos = _upbit_pos()
    entry, cur = resolve_exit_prices(pos, 103 / 1350, 1350)
    assert entry == 104
    assert abs(cur - 103) < 0.01


def test_custom_exit_triggers_when_already_past_sl():
    pos = _upbit_pos()
    cfg = AppConfig()
    ok, reason = custom_exit_triggered(pos, 103 / 1350, 1350, cfg)
    assert ok is True
    assert "손절" in reason


def test_custom_exit_triggers_at_sl_price_level():
    pos = _upbit_pos(current_price_krw=103.48, current_price=103.48 / 1350)
    pos.stop_loss = (104 / 1350) * 0.995
    cfg = AppConfig()
    ok, _ = custom_exit_triggered(pos, 103.48 / 1350, 1350, cfg)
    assert ok is True


def test_custom_exit_no_trigger_above_sl():
    pos = _upbit_pos(current_price_krw=104, current_price=104 / 1350)
    cfg = AppConfig()
    ok, _ = custom_exit_triggered(pos, 104 / 1350, 1350, cfg)
    assert ok is False


def test_config_exit_manual():
    pos = _upbit_pos(custom_sl_tp=False)
    cfg = AppConfig(stop_loss_pct=0.5, take_profit_pct=10.0)
    ok, reason = config_exit_triggered(pos, 103 / 1350, 1350, cfg)
    assert ok is True
    assert reason == "손절"

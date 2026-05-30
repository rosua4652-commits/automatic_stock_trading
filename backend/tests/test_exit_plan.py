"""손익절 수동 지정 · 설정 % 자동 매도."""

from app.engine.portfolio import PortfolioManager
from app.models import AppConfig, Position


def _pos(**kw) -> Position:
    base = dict(
        symbol="CPOOLUSDT",
        base="CPOOL",
        name_ko="씨풀",
        name_en="CPOOL",
        pair_label="KRW-CPOOL",
        display="CPOOL",
        manual_quantity=100,
        auto_quantity=0,
        avg_price=0.032,
        current_price=0.032,
        stop_loss=0.031,
        take_profit=0.034,
        cost_basis_krw=10000,
    )
    base.update(kw)
    return Position(**base)


def test_set_exit_plan_custom():
    pm = PortfolioManager()
    pm.positions["CPOOLUSDT"] = _pos()
    cfg = AppConfig()
    out = pm.set_exit_plan(
        "CPOOLUSDT",
        custom_sl_tp=True,
        stop_loss_usdt=0.03,
        take_profit_usdt=0.035,
        config=cfg,
    )
    assert out is not None
    assert out.custom_sl_tp is True
    assert out.stop_loss == 0.03
    assert out.take_profit == 0.035


def test_set_exit_plan_config_pct():
    pm = PortfolioManager()
    pm.positions["CPOOLUSDT"] = _pos(custom_sl_tp=True)
    cfg = AppConfig(stop_loss_pct=3, take_profit_pct=5)
    out = pm.set_exit_plan(
        "CPOOLUSDT",
        custom_sl_tp=False,
        stop_loss_usdt=None,
        take_profit_usdt=None,
        config=cfg,
    )
    assert out is not None
    assert out.custom_sl_tp is False
    assert abs(out.stop_loss - 0.032 * 0.97) < 1e-9
    assert abs(out.take_profit - 0.032 * 1.05) < 1e-9

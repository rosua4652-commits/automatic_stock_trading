"""모의·실거래 공통 메타 로직 단위 검증."""

from app.engine.portfolio import PortfolioManager
from app.models import AppConfig, Position


def _pos(qty: float, auto: float, manual: float) -> Position:
    return Position(
        symbol="SOLUSDT",
        base="SOL",
        name_ko="솔라나",
        name_en="Solana",
        pair_label="SOL/USDT",
        display="솔라나 (SOL)",
        auto_quantity=auto,
        manual_quantity=manual,
        avg_price=1.0,
        auto_avg_price=1.0 if auto else 0,
        manual_avg_price=1.0 if manual else 0,
        current_price=1.0,
        cost_basis_krw=100_000,
        auto_cost_basis_krw=60_000 if auto else 0,
        manual_cost_basis_krw=40_000 if manual else 0,
    )


def test_live_auto_buy_meta_matches_paper_rules():
    pm = PortfolioManager()
    pm.usdt_krw = 1400
    pos = _pos(10, 10, 0)
    before = pm.position_snap(pos)
    cfg = AppConfig()
    pm.apply_live_buy_after_sync(
        pos, before, 10, 1.0, 50_000, True, cfg, reason="AI", entry_outlook="AI 자동투자"
    )
    assert pos.auto_quantity == 10
    assert pos.manual_quantity == 0
    assert pos.stop_loss > 0
    assert pos.take_profit > 0
    assert pos.excluded_from_auto is False
    assert pos.entry_outlook == "AI 자동투자"


def test_live_manual_buy_no_tp_sl():
    pm = PortfolioManager()
    pm.usdt_krw = 1400
    pos = _pos(5, 0, 5)
    before = pm.position_snap(pos)
    cfg = AppConfig()
    pm.apply_live_buy_after_sync(
        pos, before, 5, 1.0, 20_000, False, cfg, reason="수동"
    )
    assert pos.manual_quantity == 5
    assert pos.stop_loss == 0
    assert pos.take_profit == 0


def test_live_auto_sell_realized_pnl():
    pm = PortfolioManager()
    pm.usdt_krw = 1400
    pos = _pos(2, 2, 0)
    pos.auto_cost_basis_krw = 100_000
    before = pm.position_snap(pos)
    pnl = pm.apply_live_sell_after_sync(pos, before, 2, 1.1, auto_only=True)
    assert isinstance(pnl, float)
    assert pos is None or pos.auto_quantity == 0

"""실거래 포트폴리오는 업비트 API 필드로 평가."""

from app.engine.portfolio import PortfolioManager
from app.models import AppConfig, Position


def _upbit_position(**kwargs) -> Position:
    base = dict(
        symbol="CPOOLUSDT",
        base="CPOOL",
        name_ko="씨풀",
        name_en="CPOOL",
        pair_label="KRW-CPOOL",
        display="CPOOL",
        auto_quantity=0,
        manual_quantity=1000,
        avg_price=0.01,
        current_price=0.01,
        cost_basis_krw=12000,
        data_source="upbit",
        exchange_quantity=1000,
        avg_buy_price_krw=12,
        current_price_krw=11,
        valuation_krw=11000,
    )
    base.update(kwargs)
    return Position(**base)


def test_snapshot_upbit_truth_uses_exchange_fields():
    pm = PortfolioManager()
    pm.cash_krw = 37513
    pm.usdt_krw = 1400
    pm.positions["CPOOLUSDT"] = _upbit_position()

    snap = pm.snapshot({}, AppConfig(), upbit_truth=True, upbit_synced_at=1.0)

    assert snap.data_source == "upbit"
    assert snap.principal_krw == 12000
    assert snap.invested_krw == 11000
    assert snap.unrealized_pnl_krw == -1000
    assert snap.total_value_krw == 37513 + 11000
    pos = snap.positions[0]
    assert pos.exchange_quantity == 1000
    assert pos.current_value_krw == 11000


def test_resolve_costs_prefers_upbit_avg_buy():
    from app.engine.live_sync import _resolve_position_costs

    auto, man, _, _ = _resolve_position_costs(
        {"auto_cost_basis_krw": 1, "manual_cost_basis_krw": 1},
        total_qty=100,
        auto_q=0,
        manual_q=100,
        avg_buy_krw=50,
        price_krw=55,
        usdt_krw=1350,
    )
    assert man == 5000
    assert auto == 0

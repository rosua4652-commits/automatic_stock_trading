"""업비트 동기화 시 매수원금·평단 추정."""

from app.engine.live_sync import _parse_avg_buy_krw, _resolve_position_costs


def test_parse_avg_buy_krw():
    assert _parse_avg_buy_krw({"avg_buy_price": "12345.6"}) == 12345.6
    assert _parse_avg_buy_krw({"avg_buy_price": 0}) == 0.0
    assert _parse_avg_buy_krw({}) == 0.0


def test_resolve_costs_from_upbit_avg():
    auto_cost, man_cost, auto_avg, manual_avg = _resolve_position_costs(
        {},
        total_qty=100.0,
        auto_q=0.0,
        manual_q=100.0,
        avg_buy_krw=50.0,
        price_krw=55.0,
        usdt_krw=1350.0,
    )
    assert man_cost == 5000.0
    assert auto_cost == 0.0
    assert manual_avg == 50.0 / 1350.0
    assert auto_avg == 0.0


def test_resolve_costs_keeps_saved_meta():
    pm = {
        "auto_cost_basis_krw": 3000,
        "manual_cost_basis_krw": 2000,
        "auto_avg_price": 0.5,
        "manual_avg_price": 0.4,
    }
    auto_cost, man_cost, auto_avg, manual_avg = _resolve_position_costs(
        pm,
        total_qty=10.0,
        auto_q=6.0,
        manual_q=4.0,
        avg_buy_krw=999.0,
        price_krw=100.0,
        usdt_krw=1350.0,
    )
    assert auto_cost == 3000
    assert man_cost == 2000
    assert auto_avg == 0.5
    assert manual_avg == 0.4


def test_resolve_sl_tp_ref_price_manual_only():
    """수동만 보유 시에도 평단 기준 원금 추정."""
    _, man_cost, _, manual_avg = _resolve_position_costs(
        {},
        total_qty=1000.0,
        auto_q=0.0,
        manual_q=1000.0,
        avg_buy_krw=12.34,
        price_krw=11.0,
        usdt_krw=1400.0,
    )
    assert man_cost == 12340.0
    assert manual_avg > 0

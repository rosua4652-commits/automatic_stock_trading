"""업비트 체결 파싱 · 평단 동기화."""

from app.engine.live_sync import _resolve_position_costs
from app.market.upbit_order_fill import parse_upbit_order_fill


def test_parse_order_fill_from_trades():
    order = {
        "executed_volume": "10",
        "trades": [
            {"volume": "6", "funds": "600"},
            {"volume": "4", "funds": "400"},
        ],
    }
    qty, funds, px = parse_upbit_order_fill(order)
    assert qty == 10
    assert funds == 1000
    assert px == 100


def test_parse_order_fill_hint():
    order = {"executed_volume": "48.0769"}
    qty, funds, px = parse_upbit_order_fill(
        order, amount_krw_hint=5000, price_krw_hint=104
    )
    assert qty > 0
    assert funds == 5000


def test_upbit_avg_overrides_stale_meta_avg():
    pm = {"manual_avg_price": 0.25, "auto_avg_price": 0.25}
    _, _, auto_avg, manual_avg = _resolve_position_costs(
        pm,
        total_qty=48.0,
        auto_q=0.0,
        manual_q=48.0,
        avg_buy_krw=104.0,
        price_krw=103.0,
        usdt_krw=1350.0,
    )
    truth = 104.0 / 1350.0
    assert abs(manual_avg - truth) < 1e-9
    assert auto_avg == 0.0

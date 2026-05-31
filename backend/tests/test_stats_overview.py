from app.engine.stats_overview import _mode_block
from app.engine.portfolio_store import store
from app.models import AppConfig


def test_mode_block_daily_pnl_from_report():
    snap = store.paper.snapshot({}, AppConfig())
    block = _mode_block("paper", store.paper, snap, AppConfig())
    assert "daily_pnl_krw" in block
    assert "daily_pnl_pct" in block
    assert block["report"]["trade_mode"] == "paper"

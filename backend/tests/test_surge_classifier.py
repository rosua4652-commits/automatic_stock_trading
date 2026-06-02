from app.engine.surge_classifier import classify_moonshot, moonshot_sl_tp
from app.models import AppConfig


def test_moonshot_requires_momentum_and_liquidity():
    ok, _ = classify_moonshot(
        change_24h=5.0,
        volume_usdt=5_000_000,
        entry_score=40,
        entry_ok=True,
    )
    assert not ok

    ok, tag = classify_moonshot(
        change_24h=15.0,
        volume_usdt=5_000_000,
        entry_score=40,
        entry_ok=True,
    )
    assert ok
    assert "급등" in tag


def test_moonshot_news_boost_relaxes_threshold():
    cfg = AppConfig(moonshot_min_change_24h_pct=10.0)
    ok, _ = classify_moonshot(
        change_24h=6.0,
        volume_usdt=5_000_000,
        entry_score=40,
        entry_ok=True,
        news_score=30.0,
        config=cfg,
    )
    assert ok

    ok2, _ = classify_moonshot(
        change_24h=6.0,
        volume_usdt=5_000_000,
        entry_score=40,
        entry_ok=True,
        news_score=0.0,
        config=cfg,
    )
    assert not ok2


def test_moonshot_sl_tp_defaults():
    cfg = AppConfig()
    sl, tp = moonshot_sl_tp(cfg)
    assert sl == 6.0
    assert tp == 20.0

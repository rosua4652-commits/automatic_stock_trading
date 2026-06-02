import time

from app.engine.news_signals import NewsSymbolScore
from app.engine.surge_tag_expiry import (
    effective_is_news_surge,
    effective_news_score_for_moonshot,
    prune_expired_surge_active,
    sync_surge_active_from_news,
    touch_surge_active,
)
from app.models import AppConfig


def test_touch_and_prune_expired():
    meta: dict = {}
    cfg = AppConfig(surge_tag_ttl_hours=1.0, surge_auto_expire_enabled=True)
    touch_surge_active(
        meta,
        "XLMUSDT",
        "surge",
        source="news",
        headline="Test surge",
        config=cfg,
        now=1000.0,
    )
    active = meta["surge_active"]["XLMUSDT"]
    assert active["expires_at"] == 1000.0 + 3600.0

    removed = prune_expired_surge_active(meta, now=5000.0, config=cfg)
    assert removed == 1
    assert "surge_active" not in meta or "XLMUSDT" not in meta.get("surge_active", {})


def test_refresh_extends_ttl():
    meta: dict = {}
    cfg = AppConfig(surge_tag_ttl_hours=48.0)
    touch_surge_active(meta, "BTCUSDT", "surge", config=cfg, now=1000.0)
    first_exp = meta["surge_active"]["BTCUSDT"]["expires_at"]

    touch_surge_active(meta, "BTCUSDT", "surge", config=cfg, now=2000.0)
    second_exp = meta["surge_active"]["BTCUSDT"]["expires_at"]
    assert second_exp > first_exp
    assert meta["surge_active"]["BTCUSDT"]["since"] == 2000.0


def test_effective_news_surge_requires_active_entry():
    cfg = AppConfig(news_boost_min_score=25.0, surge_auto_expire_enabled=True)
    sc = NewsSymbolScore(score=40.0, sentiment="positive")
    meta: dict = {}
    assert not effective_is_news_surge(sc, "ETHUSDT", meta, cfg)

    touch_surge_active(meta, "ETHUSDT", "surge", config=cfg)
    assert effective_is_news_surge(sc, "ETHUSDT", meta, cfg)
    assert effective_news_score_for_moonshot(sc, "ETHUSDT", meta, cfg) == 40.0


def test_sync_from_news_scores_touches_tiers():
    meta: dict = {}
    cfg = AppConfig(surge_auto_expire_enabled=True)
    scores = {
        "SOLUSDT": NewsSymbolScore(
            score=50.0,
            sentiment="positive",
            llm_direction="bullish",
            headline="SOL partnership",
        ),
        "ADAUSDT": NewsSymbolScore(
            score=70.0,
            sentiment="negative",
            llm_direction="bearish",
            llm_confidence=80.0,
            headline="ADA hack",
        ),
    }
    n = sync_surge_active_from_news(meta, scores, cfg)
    assert n == 2
    assert meta["surge_active"]["SOLUSDT"]["kind"] == "surge"
    assert meta["surge_active"]["ADAUSDT"]["kind"] == "downtrend"


def test_auto_expire_disabled_preserves_meta():
    meta: dict = {"surge_active": {"X": {"kind": "surge", "expires_at": time.time() + 9999}}}
    cfg = AppConfig(surge_auto_expire_enabled=False)
    prune_expired_surge_active(meta, config=cfg)
    assert "surge_active" in meta
    assert "X" in meta["surge_active"]
    sc = NewsSymbolScore(score=40.0, sentiment="positive")
    assert effective_is_news_surge(sc, "ETHUSDT", None, cfg)


def test_sync_surge_tags_from_persisted_meta_without_news_cache():
    from app.engine.news_signals import _cache
    from app.engine.surge_manage import sync_surge_tags

    meta: dict = {}
    cfg = AppConfig(surge_auto_expire_enabled=True, surge_tag_ttl_hours=48.0)
    touch_surge_active(meta, "SOLUSDT", "surge", config=cfg, headline="SOL news")
    touch_surge_active(meta, "ADAUSDT", "downtrend", config=cfg, headline="ADA risk")

    prev_scores = _cache.get("scores")
    _cache["scores"] = {}
    try:
        tags = sync_surge_tags(
            recommendations=[],
            candidates=[],
            config=cfg,
            meta=meta,
        )
    finally:
        if prev_scores is None:
            _cache.pop("scores", None)
        else:
            _cache["scores"] = prev_scores

    assert tags.get("SOLUSDT") == "surge"
    assert tags.get("ADAUSDT") == "downtrend"

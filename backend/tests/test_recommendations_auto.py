from app.engine.backtest_learning import BacktestLearningState
from app.engine.backtest_optimizer import BacktestAccumulator
from app.engine.recommendations import filter_recommendations_for_auto
from app.models import InvestmentRecommendation


def _moon_rec(symbol: str = "PEPEUSDT", **kw) -> InvestmentRecommendation:
    base = kw.pop("base", "PEPE")
    return InvestmentRecommendation(
        symbol=symbol,
        base=base,
        name_ko="페페",
        display=f"{base}/USDT",
        pair_label=f"{base}/USDT",
        market_score=55,
        entry_score=42,
        amount_krw=100_000,
        entry_tier="moonshot",
        volume_usdt=5_000_000,
        news_surge=kw.pop("news_surge", False),
        **kw,
    )


def test_moonshot_passes_filter_with_auto_long(monkeypatch):
    monkeypatch.setattr(
        "app.engine.recommendations.load_learning_state",
        lambda: BacktestLearningState(data_maturity_pct=20.0),
    )
    monkeypatch.setattr(
        "app.engine.recommendations.symbol_passes_learning",
        lambda *a, **k: (True, "OK"),
    )
    rec = _moon_rec()
    picks = filter_recommendations_for_auto(
        [rec],
        auto_long=True,
        auto_scalp=False,
        acc=BacktestAccumulator(),
        max_picks=2,
        paper_relax_bt=True,
    )
    assert len(picks) == 1
    assert picks[0].entry_tier == "moonshot"


def test_moonshot_excluded_when_only_auto_scalp(monkeypatch):
    monkeypatch.setattr(
        "app.engine.recommendations.load_learning_state",
        lambda: BacktestLearningState(data_maturity_pct=20.0),
    )
    monkeypatch.setattr(
        "app.engine.recommendations.symbol_passes_learning",
        lambda *a, **k: (True, "OK"),
    )
    rec = _moon_rec()
    picks = filter_recommendations_for_auto(
        [rec],
        auto_long=False,
        auto_scalp=True,
        acc=BacktestAccumulator(),
        max_picks=2,
        paper_relax_bt=True,
    )
    assert picks == []


def test_news_surge_moonshot_included_with_auto_long(monkeypatch):
    monkeypatch.setattr(
        "app.engine.recommendations.load_learning_state",
        lambda: BacktestLearningState(data_maturity_pct=20.0),
    )
    monkeypatch.setattr(
        "app.engine.recommendations.symbol_passes_learning",
        lambda *a, **k: (True, "OK"),
    )
    rec = _moon_rec(symbol="DOGEUSDT", base="DOGE", news_surge=True)
    picks = filter_recommendations_for_auto(
        [rec],
        auto_long=True,
        auto_scalp=False,
        acc=BacktestAccumulator(),
        max_picks=2,
        paper_relax_bt=True,
    )
    assert len(picks) == 1
def test_sync_surge_candidates_dedupes():
    from app.engine.recommendations import sync_surge_candidates

    recs = [
        _moon_rec(),
        _moon_rec(symbol="DOGEUSDT", base="DOGE"),
    ]
    n, syms = sync_surge_candidates(recs)
    assert n == 2
    assert "PEPEUSDT" in syms
    assert "DOGEUSDT" in syms

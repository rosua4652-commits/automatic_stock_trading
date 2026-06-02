"""백테스트 AI 학습 — Gemini 모킹."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.engine.backtest_ai import (
    BacktestAiInsight,
    _parse_ai_json,
    build_symbol_summary,
    fetch_ai_insights_for_batch,
    merge_ai_insights_into_learning,
    pick_symbols_for_ai,
)
from app.engine.backtest_ai import _ai_enabled
from app.engine.backtest_learning import BacktestLearningState
from app.engine.backtest_optimizer import BacktestAccumulator, SideStats, SymbolBacktestRecord
from app.models import AppConfig


def _acc_with_symbol(sym: str, *, score: float, wr: float, trades: int = 5) -> BacktestAccumulator:
    acc = BacktestAccumulator({"symbols": {}, "cycles": 3})
    rec = SymbolBacktestRecord(symbol=sym, updated_at=1.0)
    rec.long = SideStats(
        trades=trades,
        wins=int(trades * wr / 100),
        losses=trades - int(trades * wr / 100),
        win_rate_pct=wr,
        avg_return_pct=0.5,
        best_sl_pct=3.0,
        best_tp_pct=1.2,
        score=score,
    )
    rec.short = SideStats(trades=1, wins=0, score=20.0, best_sl_pct=2.5, best_tp_pct=0.9)
    acc.symbols[sym] = rec
    return acc


def test_parse_ai_json_valid():
    raw = (
        '{"action":"block","prefer_side":"scalp","confidence":72,'
        '"reason_ko":"승률 낮고 변동성 과다"}'
    )
    ins = _parse_ai_json(raw)
    assert ins is not None
    assert ins.action == "block"
    assert ins.prefer_side == "scalp"
    assert ins.confidence == 72


def test_pick_symbols_top_and_bottom():
    acc = _acc_with_symbol("BTCUSDT", score=80, wr=70)
    acc.merge_record(
        SymbolBacktestRecord(
            symbol="DOGEUSDT",
            long=SideStats(
                trades=5,
                wins=1,
                win_rate_pct=20,
                best_sl_pct=3,
                best_tp_pct=1,
                score=25,
            ),
            updated_at=1.0,
        )
    )
    picks = pick_symbols_for_ai(acc, ["BTCUSDT", "DOGEUSDT", "ETHUSDT"], limit=5)
    assert "BTCUSDT" in picks
    assert "DOGEUSDT" in picks


def test_merge_block_adds_symbol():
    acc = _acc_with_symbol("XRPUSDT", score=30, wr=25)
    learning = BacktestLearningState()
    ins = BacktestAiInsight(
        symbol="XRPUSDT",
        side="long",
        action="block",
        confidence=70,
        reason_ko="기대값 음수",
    )
    with patch("app.engine.backtest_ai.save_learning_state"), patch.object(
        acc, "save"
    ):
        merge_ai_insights_into_learning(learning, acc, [ins])
    assert "XRPUSDT" in learning.blocked_symbols
    assert ins.applied


def test_fetch_ai_insights_mock_gemini():
    cfg = AppConfig(backtest_ai_enabled=True, gemini_api_key="AIza-test")
    acc = _acc_with_symbol("BTCUSDT", score=75, wr=60)
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                '{"action":"widen_tp","prefer_side":"long",'
                                '"confidence":68,"reason_ko":"익절 여유 확대 권장"}'
                            )
                        }
                    ]
                }
            }
        ]
    }
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    async def _run():
        with patch("httpx.AsyncClient", return_value=mock_client):
            return await fetch_ai_insights_for_batch(
                cfg, acc, ["BTCUSDT"], tickers={"BTCUSDT": {"priceChangePercent": 3.5}}
            )

    insights = asyncio.run(_run())
    assert len(insights) == 1
    assert insights[0].action == "widen_tp"
    assert insights[0].confidence == 68


def test_build_symbol_summary_regime():
    acc = _acc_with_symbol("ETHUSDT", score=55, wr=50)
    rec = acc.symbols["ETHUSDT"]
    s = build_symbol_summary(
        "ETHUSDT",
        rec,
        tickers={"ETHUSDT": {"priceChangePercent": -4.2, "quoteVolume": 1e9}},
    )
    assert s["regime_24h"] == "하락"
    assert s["change_24h_pct"] == -4.2


def test_ai_disabled_without_key():
    cfg = AppConfig(backtest_ai_enabled=True, gemini_api_key="")
    assert not _ai_enabled(cfg)

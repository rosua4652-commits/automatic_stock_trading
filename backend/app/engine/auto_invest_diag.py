"""Explain why auto-invest did or did not buy on last scan."""

from __future__ import annotations

from app.engine.backtest_learning import (
    load_learning_state,
    symbol_passes_learning,
)
from app.engine.backtest_optimizer import BacktestAccumulator
from app.engine.flash_crash_guard import is_symbol_flash_blocked
from app.models import InvestmentRecommendation


def diagnose_auto_invest(
    recs: list[InvestmentRecommendation],
    *,
    auto_long: bool,
    auto_scalp: bool,
    acc: BacktestAccumulator,
    flash_block_until: dict[str, float] | None,
    paper_relax_bt: bool = False,
) -> tuple[str, list[str]]:
    learning = load_learning_state()
    maturity = learning.data_maturity_pct
    long_n = scalp_n = watch_n = flash_n = 0
    fail_samples: list[str] = []

    for r in recs[:12]:
        sym = r.symbol.upper()
        tier = (r.entry_tier or "").lower()
        if flash_block_until and is_symbol_flash_blocked(flash_block_until, sym):
            flash_n += 1
            continue
        if tier == "watch":
            watch_n += 1
            continue
        if tier == "auto":
            long_n += 1
            if auto_long:
                ok, why = symbol_passes_learning(
                    acc, learning, sym, mode="long", paper_relax=paper_relax_bt
                )
                if not ok and len(fail_samples) < 4:
                    fail_samples.append(f"{r.base} 롱: {why}")
        elif tier == "scalp":
            scalp_n += 1
            if auto_scalp:
                ok, why = symbol_passes_learning(
                    acc, learning, sym, mode="scalp", paper_relax=paper_relax_bt
                )
                if not ok and len(fail_samples) < 4:
                    fail_samples.append(f"{r.base} 단타: {why}")

    parts = [
        f"제안 {len(recs)}건",
        f"롱후보 {long_n}",
        f"단타후보 {scalp_n}",
        f"관망 {watch_n}",
    ]
    if flash_n:
        parts.append(f"급락차단 {flash_n}")
    parts.append(f"BT성숙 {maturity:.0f}%")
    parts.append(f"롱≥{learning.long_min_bt_score:.0f} 단타≥{learning.scalp_min_bt_score:.0f}")

    summary = " · ".join(parts)
    if fail_samples:
        summary += " | " + "; ".join(fail_samples)
    elif auto_long or auto_scalp:
        if long_n == 0 and scalp_n == 0:
            summary += " | 차트/BT 통과 종목 없음 (다음 스캔)"
        elif maturity < 15 and not paper_relax_bt:
            summary += " | BT 15% 미만 — 백테스트 누적 후 자동매수"
    return summary, fail_samples

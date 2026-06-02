"""Explain why auto-invest did or did not buy on last scan."""

from __future__ import annotations

from app.engine.backtest_learning import (
    load_learning_state,
    symbol_passes_learning,
)
from app.engine.backtest_optimizer import BacktestAccumulator
from app.engine.flash_crash_guard import is_symbol_flash_blocked
from app.engine.scalp_filters import scalp_market_fit
from app.engine.recommendations import _long_auto_volume_ok
from app.models import InvestmentRecommendation


def build_auto_invest_rejects(
    recs: list[InvestmentRecommendation],
    *,
    auto_long: bool,
    auto_scalp: bool,
    acc: BacktestAccumulator,
    flash_block_until: dict[str, float] | None,
    paper_relax_bt: bool = False,
    account_mode: str = "paper",
    max_lines: int = 12,
    disabled_surge: set[str] | None = None,
) -> list[str]:
    """UI 고정 표시용 — 종목별 탈락 사유."""
    learning = load_learning_state()
    acc = acc or BacktestAccumulator()
    blocked = disabled_surge or set()
    out: list[str] = []

    for r in recs[:20]:
        if len(out) >= max_lines:
            break
        sym = r.symbol.upper()
        tier = (r.entry_tier or "").lower()
        base = r.base or sym.replace("USDT", "")

        if flash_block_until and is_symbol_flash_blocked(flash_block_until, sym):
            out.append(f"{base}: 급락 차단")
            continue
        if tier == "watch":
            continue

        if tier == "scalp":
            if not auto_scalp:
                continue
            ok_liq, why_liq = scalp_market_fit(
                volume_usdt=float(getattr(r, "volume_usdt", 0) or 0),
                change_24h=float(getattr(r, "change_24h", 0) or 0),
            )
            if not ok_liq:
                out.append(f"{base} 단타: {why_liq}")
                continue
            ok, why = symbol_passes_learning(
                acc,
                learning,
                sym,
                mode="scalp",
                paper_relax=paper_relax_bt,
                account_mode=account_mode,
            )
            if not ok:
                out.append(f"{base} 단타: {why}")
        elif tier == "moonshot":
            if sym in blocked:
                out.append(f"{base} 급등: 사용자 비활성")
                continue
            if not auto_long:
                out.append(f"{base} 급등: 롱 자동매수 꺼짐 (단타만 켜짐)")
                continue
            ok_vol, why_vol = _long_auto_volume_ok(
                float(getattr(r, "volume_usdt", 0) or 0)
            )
            if not ok_vol:
                out.append(f"{base} 급등: {why_vol}")
                continue
            ok, why = symbol_passes_learning(
                acc,
                learning,
                sym,
                mode="moonshot",
                paper_relax=paper_relax_bt,
                account_mode=account_mode,
            )
            if not ok:
                out.append(f"{base} 급등: {why}")
        elif tier == "auto":
            if not auto_long:
                continue
            ok_vol, why_vol = _long_auto_volume_ok(
                float(getattr(r, "volume_usdt", 0) or 0)
            )
            if not ok_vol:
                out.append(f"{base} 롱: {why_vol}")
                continue
            ok, why = symbol_passes_learning(
                acc,
                learning,
                sym,
                mode="long",
                paper_relax=paper_relax_bt,
                account_mode=account_mode,
            )
            if not ok:
                out.append(f"{base} 롱: {why}")

    return out


def diagnose_auto_invest(
    recs: list[InvestmentRecommendation],
    *,
    auto_long: bool,
    auto_scalp: bool,
    acc: BacktestAccumulator,
    flash_block_until: dict[str, float] | None,
    paper_relax_bt: bool = False,
    account_mode: str = "paper",
    disabled_surge: set[str] | None = None,
) -> tuple[str, list[str]]:
    learning = load_learning_state()
    maturity = learning.data_maturity_pct
    long_n = scalp_n = moon_n = watch_n = flash_n = 0
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
                ok_vol, why_vol = _long_auto_volume_ok(
                    float(getattr(r, "volume_usdt", 0) or 0)
                )
                if not ok_vol and len(fail_samples) < 4:
                    fail_samples.append(f"{r.base} 롱: {why_vol}")
                    continue
                ok, why = symbol_passes_learning(
                    acc,
                    learning,
                    sym,
                    mode="long",
                    paper_relax=paper_relax_bt,
                    account_mode=account_mode,
                )
                if not ok and len(fail_samples) < 4:
                    fail_samples.append(f"{r.base} 롱: {why}")
        elif tier == "moonshot":
            moon_n += 1
            blocked = disabled_surge or set()
            if sym in blocked:
                if len(fail_samples) < 4:
                    fail_samples.append(f"{r.base} 급등: 사용자 비활성")
                continue
            if auto_long:
                ok_vol, why_vol = _long_auto_volume_ok(
                    float(getattr(r, "volume_usdt", 0) or 0)
                )
                if not ok_vol and len(fail_samples) < 4:
                    fail_samples.append(f"{r.base} 급등: {why_vol}")
                    continue
                ok, why = symbol_passes_learning(
                    acc,
                    learning,
                    sym,
                    mode="moonshot",
                    paper_relax=paper_relax_bt,
                    account_mode=account_mode,
                )
                if not ok and len(fail_samples) < 4:
                    fail_samples.append(f"{r.base} 급등: {why}")
        elif tier == "scalp":
            scalp_n += 1
            if auto_scalp:
                ok, why = symbol_passes_learning(
                    acc,
                    learning,
                    sym,
                    mode="scalp",
                    paper_relax=paper_relax_bt,
                    account_mode=account_mode,
                )
                if not ok and len(fail_samples) < 4:
                    fail_samples.append(f"{r.base} 단타: {why}")

    parts = [
        f"제안 {len(recs)}건",
        f"롱후보 {long_n}",
        f"급등후보 {moon_n}",
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
        if long_n == 0 and scalp_n == 0 and moon_n == 0:
            summary += " | 차트/BT 통과 종목 없음 (다음 스캔)"
        elif maturity < 15 and not paper_relax_bt:
            summary += " | BT 15% 미만 — 백테스트 누적 후 자동매수"
    if moon_n > 0 and not auto_long:
        summary += f" | 급등 {moon_n}건 — 롱 켜야 자동매수"
    return summary, fail_samples

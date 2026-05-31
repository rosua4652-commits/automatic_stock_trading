"""단타(스캘핑) — 유동성·변동성 최소 기준 (자동 매수용)."""

from __future__ import annotations

from app.config import settings


def scalp_market_fit(
    *,
    volume_usdt: float,
    change_24h: float,
    min_volume_usdt: float | None = None,
    min_abs_change_24h: float | None = None,
) -> tuple[bool, str]:
    """
    자동 단타 진입 전 시장 적합성.
    차트만 통과한 저유동·저변동 종목은 제외.
    """
    min_vol = float(
        min_volume_usdt
        if min_volume_usdt is not None
        else getattr(settings, "scalp_min_quote_volume_usdt", 2_000_000.0)
    )
    min_chg = float(
        min_abs_change_24h
        if min_abs_change_24h is not None
        else getattr(settings, "scalp_min_abs_change_24h_pct", 2.0)
    )
    vol = max(float(volume_usdt or 0), 0.0)
    chg = float(change_24h or 0.0)
    blockers: list[str] = []
    if vol < min_vol:
        blockers.append(
            f"24h 거래대금 {vol / 1_000_000:.1f}M USDT "
            f"(단타 기준 ≥{min_vol / 1_000_000:.0f}M)"
        )
    if abs(chg) < min_chg:
        blockers.append(
            f"24h 변동 {chg:+.1f}% (단타 기준 |변동|≥{min_chg:.1f}%)"
        )
    if blockers:
        return False, " / ".join(blockers)
    return True, ""


def apply_scalp_liquidity_to_candidate(cand) -> None:
    """차트 단타 가능이어도 시장이 얕으면 자동 단타 플래그만 끔."""
    if not getattr(cand, "entry_scalp_ok", False):
        return
    ok, why = scalp_market_fit(
        volume_usdt=getattr(cand, "volume_usdt", 0.0),
        change_24h=getattr(cand, "change_24h", 0.0),
    )
    if ok:
        return
    cand.entry_scalp_ok = False
    detail = getattr(cand, "entry_detail", "") or ""
    tag = f"단타 자동 제외 — {why}"
    if tag not in detail:
        cand.entry_detail = f"{detail} · {tag}" if detail else tag

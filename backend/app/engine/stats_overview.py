"""통계 탭 — 모의·실거래 동시 요약."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

KST = timezone(timedelta(hours=9))

from app.engine.daily_report import build_daily_report
from app.engine.portfolio import PortfolioManager
from app.engine.risk_manager import ensure_mode_equity_start, mode_equity_start
from app.models import AppConfig, PortfolioSnapshot
from app.storage.credentials import has_api_keys


def _coin_value_krw(snap: PortfolioSnapshot) -> float:
    return sum(float(p.current_value_krw or 0) for p in snap.positions)


def _mode_block(
    mode: str,
    mgr: PortfolioManager,
    snap: PortfolioSnapshot,
    config: AppConfig,
) -> dict[str, Any]:
    state = ensure_mode_equity_start(
        mode, snap.total_value_krw, mgr.realized_pnl_krw
    )
    start = mode_equity_start(state, mode)
    if start <= 0:
        start = max(snap.total_value_krw, 1.0)
    daily_pnl = snap.total_value_krw - start
    daily_pct = daily_pnl / start * 100.0
    report = build_daily_report(
        mgr.trades,
        snap,
        config,
        realized_pnl_krw=mgr.realized_pnl_krw,
        equity_start_krw=start,
    )
    report["trade_mode"] = mode
    return {
        "mode": mode,
        "total_value_krw": round(snap.total_value_krw, 0),
        "cash_krw": round(snap.cash_krw, 0),
        "coin_value_krw": round(_coin_value_krw(snap), 0),
        "daily_pnl_krw": round(daily_pnl, 0),
        "daily_pnl_pct": round(daily_pct, 2),
        "positions_count": len(snap.positions),
        "realized_pnl_krw": round(mgr.realized_pnl_krw, 0),
        "report": report,
        "portfolio": snap.model_dump(),
        "trades": [t.model_dump() for t in mgr.trades[-500:]],
    }


async def build_stats_overview(engine, store, config: AppConfig) -> dict[str, Any]:
    prices = await engine.prices_map()
    if has_api_keys(config):
        try:
            await store.sync_live(config)
        except Exception:
            pass

    raw = store._live_meta.get("upbit_snapshot")
    upbit_synced_at = None
    if raw and isinstance(raw, dict):
        upbit_synced_at = raw.get("synced_at")

    paper_snap = store.paper.snapshot(prices, config)
    live_snap = store.live.snapshot(
        prices,
        config,
        upbit_truth=bool(raw),
        upbit_synced_at=upbit_synced_at,
    )

    active = config.trade_mode.value
    return {
        "ok": True,
        "active_mode": active,
        "day_kst": datetime.now(KST).strftime("%Y-%m-%d"),
        "paper": _mode_block("paper", store.paper, paper_snap, config),
        "live": _mode_block("live", store.live, live_snap, config),
        "live_linked": bool(raw) or has_api_keys(config),
    }

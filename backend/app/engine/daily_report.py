"""당일 매매·손익 요약 (모의/실거래 포트폴리오별)."""

from __future__ import annotations

import csv
import io
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.engine.risk_manager import load_risk_state, peek_mode_equity_start
from app.engine.trade_feedback import _mode_from_outlook
from app.models import AppConfig, PortfolioSnapshot, TradeEvent

KST = timezone(timedelta(hours=9))


def _day_bounds_kst() -> tuple[float, float]:
    now = datetime.now(KST)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.timestamp(), end.timestamp()


def _trade_mode_label(t: TradeEvent) -> str:
    if not t.is_auto:
        return "수동"
    return _mode_from_outlook(getattr(t, "entry_outlook", "") or t.reason or "")


def build_daily_report(
    trades: list[TradeEvent],
    snap: PortfolioSnapshot,
    config: AppConfig,
    *,
    realized_pnl_krw: float,
    account_mode: str,
    equity_start_krw: float | None = None,
) -> dict[str, Any]:
    """account_mode: paper | live — 리스크·당일 손익은 해당 모드만."""
    mode = "live" if str(account_mode).lower() == "live" else "paper"
    t0, t1 = _day_bounds_kst()
    day_trades = [t for t in trades if t0 <= float(t.ts or 0) < t1]
    sells = [t for t in day_trades if (t.side or "").upper() == "SELL"]
    buys = [t for t in day_trades if (t.side or "").upper() == "BUY"]

    if equity_start_krw is not None and equity_start_krw > 0:
        start_eq = max(float(equity_start_krw), 1.0)
    else:
        peek = peek_mode_equity_start(mode)
        start_eq = max(peek, 1.0) if peek > 0 else max(snap.total_value_krw, 1.0)

    daily_pnl = snap.total_value_krw - start_eq
    daily_pct = daily_pnl / start_eq * 100.0

    risk = load_risk_state(mode)

    wins = losses = 0
    long_sells = scalp_sells = manual_sells = 0
    for t in sells:
        reason = t.reason or ""
        sell_mode = _trade_mode_label(t)
        if sell_mode == "scalp":
            scalp_sells += 1
        elif sell_mode == "long":
            long_sells += 1
        else:
            manual_sells += 1
        if "익절" in reason or "take profit" in reason.lower():
            wins += 1
        elif "손절" in reason or "stop" in reason.lower():
            losses += 1

    mdd_pct = round(min(0.0, daily_pct), 2) if daily_pct < 0 else 0.0

    sell_n = len(sells)
    win_rate = (wins / sell_n * 100.0) if sell_n else 0.0

    return {
        "day_kst": datetime.now(KST).strftime("%Y-%m-%d"),
        "generated_at": time.time(),
        "trade_mode": mode,
        "buys_count": len(buys),
        "sells_count": sell_n,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(win_rate, 1),
        "daily_pnl_krw": round(daily_pnl, 0),
        "daily_pnl_pct": round(daily_pct, 2),
        "mdd_pct": round(mdd_pct, 2),
        "long_sells": long_sells,
        "scalp_sells": scalp_sells,
        "manual_sells": manual_sells,
        "total_equity_krw": round(snap.total_value_krw, 0),
        "kill_switch": bool(risk.kill_switch),
        "kill_reason": risk.kill_reason or "",
        "open_positions": len(snap.positions),
    }


def daily_report_csv(report: dict[str, Any], trades: list[TradeEvent]) -> str:
    t0, t1 = _day_bounds_kst()
    day_trades = [t for t in trades if t0 <= float(t.ts or 0) < t1]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["field", "value"])
    for k, v in report.items():
        w.writerow([k, v])
    w.writerow([])
    w.writerow(["ts", "symbol", "side", "amount_krw", "reason", "is_auto"])
    for t in sorted(day_trades, key=lambda x: x.ts):
        w.writerow(
            [
                datetime.fromtimestamp(t.ts, KST).isoformat(),
                t.symbol,
                t.side,
                t.amount_krw,
                (t.reason or "")[:120],
                t.is_auto,
            ]
        )
    return buf.getvalue()

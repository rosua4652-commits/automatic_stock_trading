"""모의·실거래 체결 결과 → 학습 파라미터 피드백 (BT와 별도, 계정별 차단)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.storage.persistence import load_backtest_state, save_backtest_state


@dataclass
class ExecutionRecord:
    symbol: str
    mode: str  # long | scalp | unknown
    account: str  # paper | live
    pnl_pct: float
    pnl_krw: float
    won: bool
    reason: str
    ts: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "mode": self.mode,
            "account": self.account,
            "pnl_pct": round(self.pnl_pct, 3),
            "pnl_krw": round(self.pnl_krw, 0),
            "won": self.won,
            "reason": self.reason[:80],
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ExecutionRecord:
        acct = str(d.get("account") or "paper").lower()
        return cls(
            symbol=str(d.get("symbol") or "").upper(),
            mode=str(d.get("mode") or "unknown"),
            account="live" if acct == "live" else "paper",
            pnl_pct=float(d.get("pnl_pct") or 0),
            pnl_krw=float(d.get("pnl_krw") or 0),
            won=bool(d.get("won")),
            reason=str(d.get("reason") or ""),
            ts=float(d.get("ts") or 0),
        )


def _mode_from_outlook(outlook: str) -> str:
    o = (outlook or "").lower()
    if "단타" in o:
        return "scalp"
    if "롱" in o:
        return "long"
    return "long"


def _feedback_key(account: str) -> str:
    return (
        "execution_feedback_live"
        if str(account).lower() == "live"
        else "execution_feedback_paper"
    )


def _load_feedback_rows(account: str) -> list[ExecutionRecord]:
    raw = load_backtest_state()
    key = _feedback_key(account)
    rows = raw.get(key) or raw.get("execution_feedback") or []
    if not isinstance(rows, list):
        return []
    out: list[ExecutionRecord] = []
    for r in rows[-200:]:
        if isinstance(r, dict):
            rec = ExecutionRecord.from_dict(r)
            if rec.account == ("live" if account == "live" else "paper"):
                out.append(rec)
    return out


def _save_feedback_rows(account: str, rows: list[ExecutionRecord]) -> None:
    raw = load_backtest_state()
    key = _feedback_key(account)
    raw[key] = [r.to_dict() for r in rows[-200:]]
    save_backtest_state(raw)


def record_execution(
    symbol: str,
    *,
    account: str,
    entry_outlook: str,
    pnl_krw: float,
    cost_basis_krw: float,
    reason: str,
) -> str:
    """매도 체결 후 호출 — 해당 계정(모의/실거래) 체결 학습만 갱신."""
    from app.engine.backtest_learning import load_learning_state, save_learning_state

    acct = "live" if str(account).lower() == "live" else "paper"
    sym = symbol.upper()
    cost = max(cost_basis_krw, 1.0)
    pnl_pct = pnl_krw / cost * 100
    mode = _mode_from_outlook(entry_outlook)
    won = pnl_krw >= 0
    rec = ExecutionRecord(
        symbol=sym,
        mode=mode,
        account=acct,
        pnl_pct=pnl_pct,
        pnl_krw=pnl_krw,
        won=won,
        reason=reason,
        ts=time.time(),
    )
    rows = _load_feedback_rows(acct)
    rows.append(rec)
    _save_feedback_rows(acct, rows)

    learning = load_learning_state()
    acct_rows = _load_feedback_rows(acct)
    recent = acct_rows[-30:]
    if recent:
        wins = sum(1 for r in recent if r.won)
        if acct == "paper":
            learning.execution_win_rate = wins / len(recent) * 100
        learning.execution_feedback_count = len(acct_rows)

    blocked = set(
        learning.execution_blocked_live
        if acct == "live"
        else learning.execution_blocked_paper
    )
    sym_recent = [r for r in rows if r.symbol == sym][-5:]
    losses = sum(1 for r in sym_recent if not r.won)
    if len(sym_recent) >= 3 and losses >= 3:
        blocked.add(sym)
    if acct == "live":
        learning.execution_blocked_live = sorted(blocked)[-80:]
    else:
        learning.execution_blocked_paper = sorted(blocked)[-80:]

    msg_parts: list[str] = []
    if len(recent) >= 5 and acct == "paper":
        wr = learning.execution_win_rate
        if wr < 40:
            learning.long_min_bt_score = min(58.0, learning.long_min_bt_score + 1.0)
            learning.scalp_min_bt_score = min(55.0, learning.scalp_min_bt_score + 1.0)
            msg_parts.append(f"체결 승률 {wr:.0f}% 낮음 → 진입 기준 +1")
        elif wr > 62 and learning.long_min_bt_score > 38:
            learning.long_min_bt_score = max(36.0, learning.long_min_bt_score - 0.5)
            learning.scalp_min_bt_score = max(34.0, learning.scalp_min_bt_score - 0.5)
            msg_parts.append(f"체결 승률 {wr:.0f}% → 기준 소폭 완화")

    tag = "실거래" if acct == "live" else "모의"
    learning.last_adjust_message = (
        f"[{tag}] 체결 {'익' if won else '손'} {sym} {pnl_pct:+.1f}%"
        + (f" · {' · '.join(msg_parts)}" if msg_parts else "")
    )
    learning.updated_at = time.time()
    save_learning_state(learning)
    return learning.last_adjust_message


def record_paper_execution(
    symbol: str,
    *,
    entry_outlook: str,
    pnl_krw: float,
    cost_basis_krw: float,
    reason: str,
) -> str:
    return record_execution(
        symbol,
        account="paper",
        entry_outlook=entry_outlook,
        pnl_krw=pnl_krw,
        cost_basis_krw=cost_basis_krw,
        reason=reason,
    )


def record_live_execution(
    symbol: str,
    *,
    entry_outlook: str,
    pnl_krw: float,
    cost_basis_krw: float,
    reason: str,
) -> str:
    return record_execution(
        symbol,
        account="live",
        entry_outlook=entry_outlook,
        pnl_krw=pnl_krw,
        cost_basis_krw=cost_basis_krw,
        reason=reason,
    )


def symbol_blocked_by_execution(symbol: str, account_mode: str = "paper") -> bool:
    from app.engine.backtest_learning import load_learning_state, _execution_blocked

    learning = load_learning_state()
    return symbol.upper() in _execution_blocked(learning, account_mode)


def execution_stats(account_mode: str = "paper") -> dict[str, Any]:
    rows = _load_feedback_rows(account_mode)
    if not rows:
        return {"count": 0, "win_rate": 0.0}
    wins = sum(1 for r in rows if r.won)
    return {
        "count": len(rows),
        "win_rate": round(wins / len(rows) * 100, 1),
        "recent": [r.to_dict() for r in rows[-5:]],
    }

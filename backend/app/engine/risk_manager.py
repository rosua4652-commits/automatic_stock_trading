"""일손실 킬 스위치 · 자동투자 리스크 게이트 (모의 우선)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.engine.paper_validation import check_paper_validation_for_live
from app.engine.trading_hours import auto_buy_window_open
from app.models import AppConfig, PortfolioSnapshot

KST = timezone(timedelta(hours=9))
RISK_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "risk_state.json"


@dataclass
class RiskDayState:
    day_key: str = ""
    equity_start_krw: float = 0.0
    realized_start_krw: float = 0.0
    kill_switch: bool = False
    kill_reason: str = ""
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "day_key": self.day_key,
            "equity_start_krw": round(self.equity_start_krw, 0),
            "realized_start_krw": round(self.realized_start_krw, 0),
            "kill_switch": self.kill_switch,
            "kill_reason": self.kill_reason,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> RiskDayState:
        if not d:
            return cls()
        return cls(
            day_key=str(d.get("day_key") or ""),
            equity_start_krw=float(d.get("equity_start_krw") or 0),
            realized_start_krw=float(d.get("realized_start_krw") or 0),
            kill_switch=bool(d.get("kill_switch")),
            kill_reason=str(d.get("kill_reason") or ""),
            updated_at=float(d.get("updated_at") or 0),
        )


def _today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _load_raw() -> dict[str, Any]:
    if not RISK_FILE.is_file():
        return {}
    try:
        return json.loads(RISK_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_raw(data: dict[str, Any]) -> None:
    RISK_FILE.parent.mkdir(parents=True, exist_ok=True)
    RISK_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_risk_state() -> RiskDayState:
    return RiskDayState.from_dict(_load_raw())


def save_risk_state(state: RiskDayState) -> None:
    _save_raw(state.to_dict())


def _ensure_day(
    state: RiskDayState,
    *,
    total_equity: float,
    realized_pnl_krw: float,
) -> RiskDayState:
    today = _today_kst()
    if state.day_key != today:
        state = RiskDayState(
            day_key=today,
            equity_start_krw=max(total_equity, 1.0),
            realized_start_krw=realized_pnl_krw,
            kill_switch=False,
            kill_reason="",
            updated_at=time.time(),
        )
        save_risk_state(state)
    elif state.equity_start_krw <= 0:
        state.equity_start_krw = max(total_equity, 1.0)
        state.realized_start_krw = realized_pnl_krw
        state.updated_at = time.time()
        save_risk_state(state)
    return state


def evaluate_daily_risk(
    config: AppConfig,
    snap: PortfolioSnapshot,
    *,
    realized_pnl_krw: float,
) -> tuple[RiskDayState, float, float]:
    """(state, daily_pnl_krw, daily_pnl_pct) — 초과 시 kill_switch 설정."""
    state = _ensure_day(
        load_risk_state(),
        total_equity=snap.total_value_krw,
        realized_pnl_krw=realized_pnl_krw,
    )
    start_eq = max(state.equity_start_krw, 1.0)
    daily_pnl = snap.total_value_krw - start_eq
    daily_pct = daily_pnl / start_eq * 100

    limit = float(getattr(config, "daily_loss_limit_pct", 5.0) or 5.0)
    if not state.kill_switch and daily_pct <= -abs(limit):
        state.kill_switch = True
        state.kill_reason = (
            f"일손실 한도 {limit:.1f}% 초과 (당일 {daily_pct:+.2f}% · "
            f"{daily_pnl:+,.0f}원) — 자동 매수 중지"
        )
        state.updated_at = time.time()
        save_risk_state(state)
    return state, daily_pnl, daily_pct


def check_position_weight(
    config: AppConfig,
    snap: PortfolioSnapshot,
    symbol: str,
    add_krw: float,
) -> tuple[bool, str]:
    max_w = float(getattr(config, "max_position_weight_pct", 0) or 0)
    if max_w <= 0 or add_krw <= 0:
        return True, ""
    total = max(float(snap.total_value_krw or 0), 1.0)
    cur = 0.0
    for p in snap.positions:
        if p.symbol.upper() == symbol.upper():
            cur = float(p.current_value_krw or 0)
            break
    pct = (cur + add_krw) / total * 100.0
    if pct > max_w + 0.05:
        return (
            False,
            f"종목 비중 {pct:.1f}% > 한도 {max_w:.1f}% ({symbol})",
        )
    return True, ""


def check_auto_invest_allowed(
    config: AppConfig,
    snap: PortfolioSnapshot,
    *,
    realized_pnl_krw: float,
    is_paper: bool,
) -> tuple[bool, str, RiskDayState]:
    if not is_paper and not getattr(config, "allow_live_auto_invest", False):
        ok_days, days_msg = check_paper_validation_for_live(config, is_paper=False)
        if not ok_days:
            return False, days_msg, load_risk_state()
        return False, "실거래 자동투자 비활성 — 모의 검증 후 설정에서 허용", load_risk_state()

    hours_ok, hours_msg = auto_buy_window_open(config)
    if not hours_ok:
        return False, hours_msg, load_risk_state()

    state, daily_pnl, daily_pct = evaluate_daily_risk(
        config, snap, realized_pnl_krw=realized_pnl_krw
    )
    if state.kill_switch:
        return False, state.kill_reason or "일손실 킬 스위치 작동 중", state

    max_pos = int(getattr(config, "max_positions", 0) or 0)
    if max_pos > 0 and len(snap.positions) >= max_pos:
        return (
            False,
            f"최대 보유 {max_pos}종 도달 — 신규 자동 매수 대기",
            state,
        )
    return True, f"리스크 OK · 당일 {daily_pct:+.2f}% ({daily_pnl:+,.0f}원)", state


def reset_risk_day_baseline(total_equity_krw: float, realized_pnl_krw: float = 0.0) -> None:
    """모의 초기화 후 당일 기준 자산 재설정."""
    state = RiskDayState(
        day_key=_today_kst(),
        equity_start_krw=max(float(total_equity_krw), 1.0),
        realized_start_krw=float(realized_pnl_krw),
        kill_switch=False,
        kill_reason="",
        updated_at=time.time(),
    )
    save_risk_state(state)


def reset_kill_switch() -> str:
    state = load_risk_state()
    state.kill_switch = False
    state.kill_reason = ""
    state.updated_at = time.time()
    save_risk_state(state)
    return "일손실 킬 스위치 해제 (당일 기준 리셋)"

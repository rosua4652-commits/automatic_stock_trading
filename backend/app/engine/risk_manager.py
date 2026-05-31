"""일손실 킬 스위치 · 당일 기준 자산 — 모의/실거래 파일 완전 분리."""

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
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
RISK_LEGACY_FILE = DATA_DIR / "risk_state.json"
RISK_PAPER_FILE = DATA_DIR / "risk_state_paper.json"
RISK_LIVE_FILE = DATA_DIR / "risk_state_live.json"


@dataclass
class ModeRiskState:
    """모의 또는 실거래 전용 — 서로 다른 JSON 파일에 저장."""

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
    def from_dict(cls, d: dict[str, Any] | None) -> ModeRiskState:
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


def _norm_mode(mode: str) -> str:
    return "live" if str(mode).lower() == "live" else "paper"


def _risk_path(mode: str) -> Path:
    return RISK_LIVE_FILE if _norm_mode(mode) == "live" else RISK_PAPER_FILE


def _today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _load_raw(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_raw(path: Path, data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _migrate_legacy_risk_files() -> None:
    """구 risk_state.json → paper/live 분리 (1회)."""
    if not RISK_LEGACY_FILE.is_file():
        return
    if RISK_PAPER_FILE.is_file() and RISK_LIVE_FILE.is_file():
        return
    try:
        leg = json.loads(RISK_LEGACY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(leg, dict):
        return

    ks_mode = str(leg.get("kill_switch_mode") or "").lower()
    paper_eq = float(
        leg.get("paper_equity_start_krw") or leg.get("equity_start_krw") or 0
    )
    live_eq = float(leg.get("live_equity_start_krw") or 0)
    if live_eq <= 0 and ks_mode == "live":
        live_eq = float(leg.get("equity_start_krw") or 0)
    if paper_eq <= 0 and ks_mode != "live":
        paper_eq = float(leg.get("equity_start_krw") or 0)

    if not RISK_PAPER_FILE.is_file():
        paper = ModeRiskState(
            day_key=str(leg.get("day_key") or ""),
            equity_start_krw=max(paper_eq, 0.0),
            realized_start_krw=float(leg.get("realized_start_krw") or 0),
            kill_switch=bool(leg.get("kill_switch"))
            and ks_mode in ("", "paper"),
            kill_reason=str(leg.get("kill_reason") or "")
            if ks_mode in ("", "paper")
            else "",
            updated_at=float(leg.get("updated_at") or 0),
        )
        _save_raw(RISK_PAPER_FILE, paper.to_dict())

    if not RISK_LIVE_FILE.is_file():
        live = ModeRiskState(
            day_key=str(leg.get("day_key") or ""),
            equity_start_krw=max(live_eq, 0.0),
            realized_start_krw=0.0,
            kill_switch=bool(leg.get("kill_switch")) and ks_mode == "live",
            kill_reason=str(leg.get("kill_reason") or "") if ks_mode == "live" else "",
            updated_at=float(leg.get("updated_at") or 0),
        )
        _save_raw(RISK_LIVE_FILE, live.to_dict())


def load_risk_state(mode: str = "paper") -> ModeRiskState:
    _migrate_legacy_risk_files()
    mode = _norm_mode(mode)
    return ModeRiskState.from_dict(_load_raw(_risk_path(mode)))


def save_risk_state(state: ModeRiskState, mode: str) -> None:
    _save_raw(_risk_path(_norm_mode(mode)), state.to_dict())


def peek_mode_equity_start(mode: str) -> float:
    """통계 표시용 — 파일만 읽고 쓰지 않음."""
    state = load_risk_state(mode)
    if state.day_key != _today_kst():
        return 0.0
    return float(state.equity_start_krw or 0)


def _ensure_day(
    state: ModeRiskState,
    *,
    total_equity: float,
    realized_pnl_krw: float,
) -> ModeRiskState:
    today = _today_kst()
    if state.day_key != today:
        state = ModeRiskState(
            day_key=today,
            equity_start_krw=max(total_equity, 1.0),
            realized_start_krw=realized_pnl_krw,
            kill_switch=False,
            kill_reason="",
            updated_at=time.time(),
        )
    elif state.equity_start_krw <= 0:
        state.equity_start_krw = max(total_equity, 1.0)
        state.realized_start_krw = realized_pnl_krw
        state.updated_at = time.time()
    return state


def ensure_mode_equity_start(
    mode: str,
    total_equity: float,
    realized_pnl_krw: float,
    *,
    persist: bool = True,
) -> ModeRiskState:
    mode = _norm_mode(mode)
    state = _ensure_day(
        load_risk_state(mode),
        total_equity=total_equity,
        realized_pnl_krw=realized_pnl_krw,
    )
    if persist:
        save_risk_state(state, mode)
    return state


def evaluate_daily_risk(
    config: AppConfig,
    snap: PortfolioSnapshot,
    *,
    realized_pnl_krw: float,
    mode: str = "paper",
) -> tuple[ModeRiskState, float, float]:
    """(state, daily_pnl_krw, daily_pnl_pct) — 해당 모드 파일만 갱신."""
    mode = _norm_mode(mode)
    state = _ensure_day(
        load_risk_state(mode),
        total_equity=snap.total_value_krw,
        realized_pnl_krw=realized_pnl_krw,
    )
    start_eq = max(state.equity_start_krw, 1.0)
    daily_pnl = snap.total_value_krw - start_eq
    daily_pct = daily_pnl / start_eq * 100

    limit = float(getattr(config, "daily_loss_limit_pct", 5.0) or 5.0)
    if not state.kill_switch and daily_pct <= -abs(limit):
        mode_label = "실거래" if mode == "live" else "모의"
        state.kill_switch = True
        state.kill_reason = (
            f"일손실 한도 {limit:.1f}% 초과 ({mode_label} · 당일 {daily_pct:+.2f}% · "
            f"{daily_pnl:+,.0f}원) — 자동 매수 중지"
        )
        state.updated_at = time.time()
    save_risk_state(state, mode)
    return state, daily_pnl, daily_pct


def kill_switch_active_for(state: ModeRiskState, mode: str) -> bool:
    _ = _norm_mode(mode)
    return bool(state.kill_switch)


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
) -> tuple[bool, str, ModeRiskState]:
    mode = "paper" if is_paper else "live"
    if not is_paper and not getattr(config, "allow_live_auto_invest", False):
        ok_days, days_msg = check_paper_validation_for_live(config, is_paper=False)
        if not ok_days:
            return False, days_msg, load_risk_state(mode)
        return (
            False,
            "실거래 자동투자 비활성 — 모의 검증 후 설정에서 허용",
            load_risk_state(mode),
        )

    hours_ok, hours_msg = auto_buy_window_open(config)
    if not hours_ok:
        return False, hours_msg, load_risk_state(mode)

    state, daily_pnl, daily_pct = evaluate_daily_risk(
        config, snap, realized_pnl_krw=realized_pnl_krw, mode=mode
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


def reset_risk_day_baseline(
    total_equity_krw: float,
    realized_pnl_krw: float = 0.0,
    *,
    mode: str = "paper",
) -> None:
    mode = _norm_mode(mode)
    eq = max(float(total_equity_krw), 1.0)
    state = ModeRiskState(
        day_key=_today_kst(),
        equity_start_krw=eq,
        realized_start_krw=float(realized_pnl_krw),
        kill_switch=False,
        kill_reason="",
        updated_at=time.time(),
    )
    save_risk_state(state, mode)


def reset_kill_switch(
    mode: str,
    total_equity_krw: float,
    realized_pnl_krw: float = 0.0,
) -> str:
    mode = _norm_mode(mode)
    reset_risk_day_baseline(
        total_equity_krw, realized_pnl_krw, mode=mode
    )
    label = "실거래" if mode == "live" else "모의"
    return f"킬 스위치 해제 · {label} 당일 기준 {max(total_equity_krw, 1):,.0f}원으로 재설정"


def on_trade_mode_switch(mode: str, total_equity_krw: float) -> None:
    """모드 전환 시 해당 모드 파일만 당일 기준 보정 (다른 모드 파일은 건드리지 않음)."""
    mode = _norm_mode(mode)
    state = load_risk_state(mode)
    if state.day_key != _today_kst() or state.equity_start_krw <= 0:
        ensure_mode_equity_start(
            mode, total_equity_krw, 0.0, persist=True
        )

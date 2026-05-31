"""백테스트 누적 → 임계값·손익절·종목 필터를 주기적으로 조정 (고정 구조 재사용 방지)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.engine.backtest_optimizer import BacktestAccumulator, SideStats
from app.storage.persistence import load_backtest_state, save_backtest_state


@dataclass
class BacktestLearningState:
    """실전·자동매수에 쓰는 학습 파라미터 (백테스트 파일에 함께 저장)."""

    long_min_bt_score: float = 42.0
    scalp_min_bt_score: float = 38.0
    long_sl_pct: float = 0.0
    long_tp_pct: float = 0.0
    scalp_sl_pct: float = 0.0
    scalp_tp_pct: float = 0.0
    recent_batch_win_rate: float = 0.0
    recent_batch_trades: int = 0
    adjust_cycles: int = 0
    blocked_symbols: list[str] = field(default_factory=list)
    last_adjust_message: str = ""
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "long_min_bt_score": round(self.long_min_bt_score, 2),
            "scalp_min_bt_score": round(self.scalp_min_bt_score, 2),
            "long_sl_pct": round(self.long_sl_pct, 2),
            "long_tp_pct": round(self.long_tp_pct, 2),
            "scalp_sl_pct": round(self.scalp_sl_pct, 2),
            "scalp_tp_pct": round(self.scalp_tp_pct, 2),
            "recent_batch_win_rate": round(self.recent_batch_win_rate, 2),
            "recent_batch_trades": self.recent_batch_trades,
            "adjust_cycles": self.adjust_cycles,
            "blocked_symbols": list(self.blocked_symbols)[-80:],
            "last_adjust_message": self.last_adjust_message,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> BacktestLearningState:
        if not d:
            return cls()
        blocked = d.get("blocked_symbols") or []
        if not isinstance(blocked, list):
            blocked = []
        return cls(
            long_min_bt_score=float(d.get("long_min_bt_score") or 42.0),
            scalp_min_bt_score=float(d.get("scalp_min_bt_score") or 38.0),
            long_sl_pct=float(d.get("long_sl_pct") or 0.0),
            long_tp_pct=float(d.get("long_tp_pct") or 0.0),
            scalp_sl_pct=float(d.get("scalp_sl_pct") or 0.0),
            scalp_tp_pct=float(d.get("scalp_tp_pct") or 0.0),
            recent_batch_win_rate=float(d.get("recent_batch_win_rate") or 0.0),
            recent_batch_trades=int(d.get("recent_batch_trades") or 0),
            adjust_cycles=int(d.get("adjust_cycles") or 0),
            blocked_symbols=[str(s).upper() for s in blocked],
            last_adjust_message=str(d.get("last_adjust_message") or ""),
            updated_at=float(d.get("updated_at") or 0.0),
        )


def load_learning_state() -> BacktestLearningState:
    raw = load_backtest_state()
    return BacktestLearningState.from_dict(raw.get("learning"))


def save_learning_state(learning: BacktestLearningState) -> None:
    raw = load_backtest_state()
    raw["learning"] = learning.to_dict()
    save_backtest_state(raw)


def _side_expectancy(st: SideStats) -> float:
    if st.trades < 1 or st.best_sl_pct <= 0:
        return 0.0
    wr = st.wins / st.trades
    return wr * st.best_tp_pct - (1 - wr) * st.best_sl_pct


def symbol_passes_learning(
    acc: BacktestAccumulator,
    learning: BacktestLearningState,
    symbol: str,
    *,
    mode: str,
) -> tuple[bool, str]:
    """mode: long | scalp"""
    sym = symbol.upper()
    if sym in learning.blocked_symbols:
        return False, "백테스트 차단 종목"
    rec = acc.symbols.get(sym)
    if not rec:
        return True, "BT 데이터 없음(신규)"
    st = rec.long if mode == "long" else rec.short
    floor = (
        learning.long_min_bt_score if mode == "long" else learning.scalp_min_bt_score
    )
    if st.trades >= 2 and st.score < floor:
        return False, f"BT점수 {st.score:.0f} < 학습기준 {floor:.0f}"
    if st.trades >= 3 and st.win_rate_pct < 38 and _side_expectancy(st) < 0:
        return False, f"BT 기대값 음수 · 승률 {st.win_rate_pct:.0f}%"
    return True, "OK"


def strategy_sl_tp(
    learning: BacktestLearningState,
    acc: BacktestAccumulator,
    symbol: str,
    *,
    mode: str,
    default_sl: float,
    default_tp: float,
) -> tuple[float, float]:
    g_sl, g_tp = acc.best_global_params(default_sl, default_tp)
    if mode == "long":
        if learning.long_sl_pct > 0:
            return learning.long_sl_pct, learning.long_tp_pct or g_tp
        rec = acc.symbols.get(symbol.upper())
        if rec and rec.long.trades >= 2 and rec.long.best_sl_pct > 0:
            return rec.long.best_sl_pct, rec.long.best_tp_pct
        return g_sl, g_tp
    # scalp — 더 타이트
    if learning.scalp_sl_pct > 0:
        return learning.scalp_sl_pct, learning.scalp_tp_pct or max(g_tp * 0.65, g_sl * 2)
    tight_sl = max(2.5, min(g_sl * 0.55, g_sl))
    tight_tp = max(tight_sl * 1.5, min(g_tp * 0.55, g_tp))
    return round(tight_sl, 2), round(tight_tp, 2)


def update_learning_from_batch(
    acc: BacktestAccumulator,
    batch_symbols: list[str],
    *,
    default_sl: float,
    default_tp: float,
) -> BacktestLearningState:
    """이번 배치 결과로 임계값·차단목록·전략별 손익절 갱신."""
    learning = load_learning_state()
    wins = trades = 0
    for sym in batch_symbols:
        rec = acc.symbols.get(sym.upper())
        if not rec:
            continue
        for st in (rec.long, rec.short):
            if st.trades < 1:
                continue
            trades += st.trades
            wins += st.wins

    if trades > 0:
        learning.recent_batch_win_rate = wins / trades * 100
        learning.recent_batch_trades = trades
    learning.adjust_cycles += 1

    g_sl, g_tp = acc.best_global_params(default_sl, default_tp)
    if learning.long_sl_pct <= 0:
        learning.long_sl_pct, learning.long_tp_pct = g_sl, g_tp
    if learning.scalp_sl_pct <= 0:
        learning.scalp_sl_pct = max(2.5, g_sl * 0.55)
        learning.scalp_tp_pct = max(learning.scalp_sl_pct * 1.8, g_tp * 0.55)

    wr = learning.recent_batch_win_rate
    # 임계값 조정 — 성과 나쁘면 엄격, 좋으면 소폭 완화
    if trades >= 5:
        if wr < 42:
            learning.long_min_bt_score = min(55.0, learning.long_min_bt_score + 1.5)
            learning.scalp_min_bt_score = min(52.0, learning.scalp_min_bt_score + 1.5)
            learning.last_adjust_message = (
                f"배치 승률 {wr:.0f}% 낮음 → 진입 기준 상향 "
                f"(롱≥{learning.long_min_bt_score:.0f} 단타≥{learning.scalp_min_bt_score:.0f})"
            )
        elif wr > 58:
            learning.long_min_bt_score = max(36.0, learning.long_min_bt_score - 0.8)
            learning.scalp_min_bt_score = max(32.0, learning.scalp_min_bt_score - 0.8)
            learning.last_adjust_message = (
                f"배치 승률 {wr:.0f}% 양호 → 진입 기준 소폭 완화"
            )
        else:
            learning.last_adjust_message = f"배치 승률 {wr:.0f}% · 기준 유지"

    # 저성과 종목 차단 (누적 4건 이상·승률·점수 모두 낮음)
    blocked = set(learning.blocked_symbols)
    for sym, rec in acc.symbols.items():
        st = rec.long
        if st.trades >= 4 and st.score < 38 and st.win_rate_pct < 40:
            blocked.add(sym)
    learning.blocked_symbols = sorted(blocked)[-80:]

    # 전역 손익절을 학습 상태에 서서히 반영 (급변 방지)
    learning.long_sl_pct = round(learning.long_sl_pct * 0.7 + g_sl * 0.3, 2)
    learning.long_tp_pct = round(learning.long_tp_pct * 0.7 + g_tp * 0.3, 2)
    learning.scalp_sl_pct = round(
        max(2.5, learning.scalp_sl_pct * 0.6 + g_sl * 0.4 * 0.55), 2
    )
    learning.scalp_tp_pct = round(
        max(learning.scalp_sl_pct * 1.5, learning.scalp_tp_pct * 0.6 + g_tp * 0.4 * 0.55),
        2,
    )
    learning.updated_at = time.time()
    save_learning_state(learning)
    return learning

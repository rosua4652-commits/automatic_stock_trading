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
    execution_win_rate: float = 0.0
    execution_feedback_count: int = 0
    data_maturity_pct: float = 0.0

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
            "execution_win_rate": round(self.execution_win_rate, 2),
            "execution_feedback_count": self.execution_feedback_count,
            "data_maturity_pct": round(self.data_maturity_pct, 1),
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
            execution_win_rate=float(d.get("execution_win_rate") or 0.0),
            execution_feedback_count=int(d.get("execution_feedback_count") or 0),
            data_maturity_pct=float(d.get("data_maturity_pct") or 0.0),
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


def compute_data_maturity(acc: BacktestAccumulator) -> float:
    """누적 종목·사이클이 많을수록 0~100."""
    depth = len(acc.symbols) * max(1, acc.cycles)
    return min(100.0, depth / 10.0)


def symbol_passes_learning(
    acc: BacktestAccumulator,
    learning: BacktestLearningState,
    symbol: str,
    *,
    mode: str,
    paper_relax: bool = False,
) -> tuple[bool, str]:
    """mode: long | scalp"""
    sym = symbol.upper()
    if sym in learning.blocked_symbols:
        return False, "학습 차단 종목(BT·체결)"
    maturity = learning.data_maturity_pct or compute_data_maturity(acc)
    rec = acc.symbols.get(sym)
    if not rec and maturity < 15:
        if paper_relax:
            return True, "모의·BT초기(차트·제안 기준)"
        return False, "BT 데이터 부족(15% 전)"
    if not rec:
        if maturity >= 25:
            return True, "BT 신규(성숙도 충분)"
        return False, "BT 미검증 종목"
    st = rec.long if mode == "long" else rec.short
    floor = (
        learning.long_min_bt_score if mode == "long" else learning.scalp_min_bt_score
    )
    # 데이터 많을수록 최소 거래 수 요구
    min_trades = 1 if maturity < 40 else (2 if maturity < 70 else 3)
    if st.trades < min_trades and maturity >= 30:
        return False, f"BT 거래 수 {st.trades} < 요구 {min_trades}"
    if st.trades >= 2 and st.score < floor:
        return False, f"BT점수 {st.score:.0f} < 학습기준 {floor:.0f}"
    if st.trades >= 3 and st.win_rate_pct < 38 and _side_expectancy(st) < 0:
        return False, f"BT 기대값 음수 · 승률 {st.win_rate_pct:.0f}%"
    return True, "OK"


def resolve_sl_tp_from_backtest(
    acc: BacktestAccumulator | None,
    learning: BacktestLearningState | None,
    symbol: str,
    *,
    mode: str,
    default_sl: float,
    default_tp: float,
) -> tuple[float, float, str]:
    """
    백테스트 그리드 탐색 결과로 손익절 % 선정.
    우선순위: 종목 BT(롱/숏) → 학습 누적(롱/단타) → BT 전역 → 설정.
    """
    sym = symbol.upper()
    mode = mode.lower()
    if mode not in ("long", "scalp", "short"):
        mode = "long"
    if mode == "short":
        mode = "scalp"

    acc = acc or BacktestAccumulator()
    learning = learning or load_learning_state()
    rec = acc.symbols.get(sym)
    st = None
    if rec:
        st = rec.long if mode == "long" else rec.short

    if st and st.trades >= 1 and st.best_sl_pct > 0 and st.score >= 32:
        return (
            round(st.best_sl_pct, 2),
            round(max(st.best_tp_pct, st.best_sl_pct * 1.2), 2),
            "BT종목",
        )

    g_sl, g_tp = acc.best_global_params(default_sl, default_tp)

    if mode == "long" and learning.long_sl_pct > 0:
        return (
            learning.long_sl_pct,
            learning.long_tp_pct or g_tp or default_tp,
            "BT학습·롱",
        )
    if mode == "scalp" and learning.scalp_sl_pct > 0:
        return (
            learning.scalp_sl_pct,
            learning.scalp_tp_pct or max(learning.scalp_sl_pct * 1.8, g_tp * 0.55),
            "BT학습·단타",
        )

    if g_sl > 0:
        if mode == "scalp":
            tight_sl = max(2.5, round(g_sl * 0.55, 2))
            tight_tp = max(tight_sl * 1.5, round(g_tp * 0.55, 2))
            return tight_sl, tight_tp, "BT전역·단타"
        return g_sl, g_tp, "BT전역"

    if mode == "scalp":
        tight_sl = max(2.5, round(default_sl * 0.55, 2))
        tight_tp = max(tight_sl * 1.5, round(default_tp * 0.55, 2))
        return tight_sl, tight_tp, "설정·단타"

    return default_sl, default_tp, "설정"


def strategy_sl_tp(
    learning: BacktestLearningState,
    acc: BacktestAccumulator,
    symbol: str,
    *,
    mode: str,
    default_sl: float,
    default_tp: float,
) -> tuple[float, float]:
    sl, tp, _ = resolve_sl_tp_from_backtest(
        acc, learning, symbol, mode=mode, default_sl=default_sl, default_tp=default_tp
    )
    return sl, tp


def format_sl_tp_label(sl_pct: float, tp_pct: float, source: str) -> str:
    return f"손절 {sl_pct:.1f}% · 익절 {tp_pct:.1f}% ({source})"


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
    learning.data_maturity_pct = compute_data_maturity(acc)
    maturity = learning.data_maturity_pct / 100.0

    g_sl, g_tp = acc.best_global_params(default_sl, default_tp)
    if learning.long_sl_pct <= 0:
        learning.long_sl_pct, learning.long_tp_pct = g_sl, g_tp
    if learning.scalp_sl_pct <= 0:
        learning.scalp_sl_pct = max(2.5, g_sl * 0.55)
        learning.scalp_tp_pct = max(learning.scalp_sl_pct * 1.8, g_tp * 0.55)

    wr = learning.recent_batch_win_rate
    # 임계값 조정 — 성과 나쁘면 엄격, 좋으면 소폭 완화
    step = 0.8 + maturity * 0.7
    if trades >= 5:
        if wr < 42:
            learning.long_min_bt_score = min(55.0, learning.long_min_bt_score + step)
            learning.scalp_min_bt_score = min(52.0, learning.scalp_min_bt_score + step)
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

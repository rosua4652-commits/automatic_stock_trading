"""백테스트 누적 → 임계값·손익절·종목 필터를 주기적으로 조정 (고정 구조 재사용 방지)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.engine.backtest_optimizer import BacktestAccumulator, SideStats
from app.storage.persistence import load_backtest_state, save_backtest_state
from app.util.numbers import as_float


@dataclass
class BacktestLearningState:
    """실전·자동매수에 쓰는 학습 파라미터 (백테스트 파일에 함께 저장)."""

    long_min_bt_score: float = 38.0
    scalp_min_bt_score: float = 35.0
    long_sl_pct: float = 0.0
    long_tp_pct: float = 0.0
    scalp_sl_pct: float = 0.0
    scalp_tp_pct: float = 0.0
    recent_batch_win_rate: float = 0.0
    recent_batch_trades: int = 0
    adjust_cycles: int = 0
    blocked_symbols: list[str] = field(default_factory=list)
    execution_blocked_paper: list[str] = field(default_factory=list)
    execution_blocked_live: list[str] = field(default_factory=list)
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
            "execution_blocked_paper": list(self.execution_blocked_paper)[-80:],
            "execution_blocked_live": list(self.execution_blocked_live)[-80:],
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
        ebp = d.get("execution_blocked_paper") or []
        ebl = d.get("execution_blocked_live") or []
        if not isinstance(ebp, list):
            ebp = []
        if not isinstance(ebl, list):
            ebl = []
        if not ebp and not ebl and blocked:
            ebp = list(blocked)
        return cls(
            long_min_bt_score=min(
                48.0, as_float(d.get("long_min_bt_score"), 38.0)
            ),
            scalp_min_bt_score=min(
                45.0, as_float(d.get("scalp_min_bt_score"), 35.0)
            ),
            long_sl_pct=as_float(d.get("long_sl_pct")),
            long_tp_pct=as_float(d.get("long_tp_pct")),
            scalp_sl_pct=as_float(d.get("scalp_sl_pct")),
            scalp_tp_pct=as_float(d.get("scalp_tp_pct")),
            recent_batch_win_rate=as_float(d.get("recent_batch_win_rate")),
            recent_batch_trades=int(d.get("recent_batch_trades") or 0),
            adjust_cycles=int(d.get("adjust_cycles") or 0),
            blocked_symbols=[str(s).upper() for s in blocked],
            execution_blocked_paper=[str(s).upper() for s in ebp],
            execution_blocked_live=[str(s).upper() for s in ebl],
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
    if st.trades < 1 or as_float(st.best_sl_pct) <= 0:
        return 0.0
    wr = st.wins / st.trades
    sl = as_float(st.best_sl_pct)
    tp = as_float(st.best_tp_pct)
    return wr * tp - (1 - wr) * sl


def _clamp_auto_sl_tp(
    mode: str,
    sl_pct: float,
    tp_pct: float,
    *,
    fee_pct: float = 0.05,
) -> tuple[float, float]:
    """
    자동투자용 손익절 — 익절은 수수료 제외 후 소폭 이익, 손절은 익절보다 넓게.
    """
    sl = as_float(sl_pct, 2.5)
    tp = as_float(tp_pct, 1.0)
    fee_rt = max(0.0, fee_pct) * 2.0
    min_tp = round(fee_rt + 0.35, 2)

    if mode == "scalp":
        tp = min(tp, 1.15)
        tp = max(tp, min_tp)
        sl = min(max(sl, 1.8), 2.8)
        sl = max(sl, tp * 1.35)
    else:
        tp = min(tp, 1.8)
        tp = max(tp, min_tp)
        sl = min(max(sl, 2.0), 3.5)
        sl = max(sl, tp * 1.25)
    return round(sl, 2), round(tp, 2)


def compute_data_maturity(acc: BacktestAccumulator) -> float:
    """누적 종목·사이클이 많을수록 0~100."""
    depth = len(acc.symbols) * max(1, acc.cycles)
    return min(100.0, depth / 10.0)


def _execution_blocked(
    learning: BacktestLearningState, account_mode: str
) -> list[str]:
    if str(account_mode).lower() == "live":
        return learning.execution_blocked_live
    return learning.execution_blocked_paper


def symbol_passes_learning(
    acc: BacktestAccumulator,
    learning: BacktestLearningState,
    symbol: str,
    *,
    mode: str,
    paper_relax: bool = False,
    account_mode: str = "paper",
) -> tuple[bool, str]:
    """mode: long | scalp · account_mode: paper | live (체결 차단만 분리)."""
    sym = symbol.upper()
    if sym in learning.blocked_symbols:
        return False, "학습 차단 종목(BT)"
    if sym in _execution_blocked(learning, account_mode):
        tag = "모의" if str(account_mode).lower() != "live" else "실거래"
        return False, f"체결 학습 차단({tag})"
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
    if st.trades >= 2 and as_float(st.score) < floor:
        return False, f"BT점수 {as_float(st.score):.0f} < 학습기준 {floor:.0f}"
    if st.trades >= 3 and as_float(st.win_rate_pct) < 38 and _side_expectancy(st) < 0:
        return False, f"BT 기대값 음수 · 승률 {as_float(st.win_rate_pct):.0f}%"
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

    if st and st.trades >= 1 and as_float(st.best_sl_pct) > 0 and as_float(st.score) >= 32:
        sl, tp = _clamp_auto_sl_tp(
            mode,
            as_float(st.best_sl_pct),
            as_float(st.best_tp_pct),
        )
        return sl, tp, "BT종목"

    d_sl = as_float(default_sl, 3.0)
    d_tp = as_float(default_tp, 1.2)
    g_sl, g_tp = acc.best_global_params(d_sl, d_tp)
    g_sl = as_float(g_sl, d_sl)
    g_tp = as_float(g_tp, d_tp)

    l_sl = as_float(learning.long_sl_pct)
    l_tp = as_float(learning.long_tp_pct)
    s_sl = as_float(learning.scalp_sl_pct)
    s_tp = as_float(learning.scalp_tp_pct)

    if mode == "long" and l_sl > 0:
        sl, tp = _clamp_auto_sl_tp(mode, l_sl, l_tp or g_tp or d_tp)
        return sl, tp, "BT학습·롱"
    if mode == "scalp" and s_sl > 0:
        sl, tp = _clamp_auto_sl_tp(mode, s_sl, s_tp or g_tp or d_tp)
        return sl, tp, "BT학습·단타"

    if g_sl > 0:
        if mode == "scalp":
            sl, tp = _clamp_auto_sl_tp(
                "scalp",
                max(1.8, g_sl * 0.85),
                max(0.7, g_tp * 0.85),
            )
            return sl, tp, "BT전역·단타"
        sl, tp = _clamp_auto_sl_tp("long", g_sl, g_tp)
        return sl, tp, "BT전역"

    if mode == "scalp":
        sl, tp = _clamp_auto_sl_tp("scalp", d_sl * 0.85, d_tp * 0.9)
        return sl, tp, "설정·단타"

    sl, tp = _clamp_auto_sl_tp("long", d_sl, d_tp)
    return sl, tp, "설정"


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

    d_sl = as_float(default_sl, 3.0)
    d_tp = as_float(default_tp, 5.0)
    g_sl, g_tp = acc.best_global_params(d_sl, d_tp)
    g_sl = as_float(g_sl, d_sl)
    g_tp = as_float(g_tp, d_tp)
    learning.long_sl_pct = as_float(learning.long_sl_pct)
    learning.long_tp_pct = as_float(learning.long_tp_pct)
    learning.scalp_sl_pct = as_float(learning.scalp_sl_pct)
    learning.scalp_tp_pct = as_float(learning.scalp_tp_pct)
    if learning.long_sl_pct <= 0:
        learning.long_sl_pct, learning.long_tp_pct = _clamp_auto_sl_tp("long", g_sl, g_tp)
    if learning.scalp_sl_pct <= 0:
        learning.scalp_sl_pct, learning.scalp_tp_pct = _clamp_auto_sl_tp(
            "scalp", max(1.8, g_sl * 0.85), max(0.7, g_tp * 0.85)
        )

    wr = learning.recent_batch_win_rate
    step = 0.5 + maturity * 0.4
    if trades >= 5:
        if wr < 42:
            learning.long_min_bt_score = min(48.0, learning.long_min_bt_score + step)
            learning.scalp_min_bt_score = min(45.0, learning.scalp_min_bt_score + step)
            learning.last_adjust_message = (
                f"배치 승률 {wr:.0f}% 낮음 → 진입 기준 상향 "
                f"(롱≥{learning.long_min_bt_score:.0f} 단타≥{learning.scalp_min_bt_score:.0f})"
            )
        elif wr > 55:
            learning.long_min_bt_score = max(34.0, learning.long_min_bt_score - 0.6)
            learning.scalp_min_bt_score = max(30.0, learning.scalp_min_bt_score - 0.6)
            learning.last_adjust_message = (
                f"배치 승률 {wr:.0f}% 양호 → 진입 기준 소폭 완화"
            )
        else:
            learning.last_adjust_message = f"배치 승률 {wr:.0f}% · 기준 유지"
            if wr < 48 and learning.long_min_bt_score > 38:
                learning.long_min_bt_score = max(38.0, learning.long_min_bt_score - 0.4)
                learning.scalp_min_bt_score = max(34.0, learning.scalp_min_bt_score - 0.4)

    # 저성과 종목 차단 (누적 4건 이상·승률·점수 모두 낮음)
    blocked = set(learning.blocked_symbols)
    for sym, rec in acc.symbols.items():
        st = rec.long
        if st.trades >= 4 and st.score < 38 and st.win_rate_pct < 40:
            blocked.add(sym)
    learning.blocked_symbols = sorted(blocked)[-80:]

    # 전역 손익절을 학습 상태에 서서히 반영 (급변 방지)
    l_sl, l_tp = _clamp_auto_sl_tp("long", g_sl, g_tp)
    s_sl, s_tp = _clamp_auto_sl_tp("scalp", max(1.8, g_sl * 0.85), max(0.7, g_tp * 0.85))
    learning.long_sl_pct = round(as_float(learning.long_sl_pct) * 0.7 + l_sl * 0.3, 2)
    learning.long_tp_pct = round(as_float(learning.long_tp_pct) * 0.7 + l_tp * 0.3, 2)
    learning.scalp_sl_pct = round(as_float(learning.scalp_sl_pct) * 0.6 + s_sl * 0.4, 2)
    learning.scalp_tp_pct = round(as_float(learning.scalp_tp_pct) * 0.6 + s_tp * 0.4, 2)
    learning.updated_at = time.time()
    save_learning_state(learning)
    return learning

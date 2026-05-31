"""백테스트 누적·파라미터 탐색 → 롱/숏·투자 제안 가중치."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.config import settings
from app.market.upbit_data import market
from app.aidi_log import get_aidi_logger
from app.storage.persistence import load_backtest_state, save_backtest_state

logger = get_aidi_logger()

# (손절%, 익절%) 후보 — 설정 주변 그리드
PARAM_GRID: list[tuple[float, float]] = [
    (3.0, 6.0),
    (4.0, 8.0),
    (5.0, 10.0),
    (6.0, 12.0),
    (7.0, 14.0),
    (8.0, 16.0),
]


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    if len(values) < period:
        return values
    alpha = 2 / (period + 1)
    out = np.empty_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


@dataclass
class SideStats:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    avg_return_pct: float = 0.0
    win_rate_pct: float = 0.0
    best_sl_pct: float = 0.0
    best_tp_pct: float = 0.0
    score: float = 0.0  # 0~100 백테스트 적합도

    def to_dict(self) -> dict[str, Any]:
        return {
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.losses,
            "avg_return_pct": round(self.avg_return_pct, 3),
            "win_rate_pct": round(self.win_rate_pct, 2),
            "best_sl_pct": self.best_sl_pct,
            "best_tp_pct": self.best_tp_pct,
            "score": round(self.score, 1),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SideStats:
        return cls(
            trades=int(d.get("trades") or 0),
            wins=int(d.get("wins") or 0),
            losses=int(d.get("losses") or 0),
            avg_return_pct=float(d.get("avg_return_pct") or 0),
            win_rate_pct=float(d.get("win_rate_pct") or 0),
            best_sl_pct=float(d.get("best_sl_pct") or 0),
            best_tp_pct=float(d.get("best_tp_pct") or 0),
            score=float(d.get("score") or 0),
        )


@dataclass
class SymbolBacktestRecord:
    symbol: str
    long: SideStats = field(default_factory=SideStats)
    short: SideStats = field(default_factory=SideStats)
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "long": self.long.to_dict(),
            "short": self.short.to_dict(),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SymbolBacktestRecord:
        return cls(
            symbol=str(d.get("symbol") or "").upper(),
            long=SideStats.from_dict(d.get("long") or {}),
            short=SideStats.from_dict(d.get("short") or {}),
            updated_at=float(d.get("updated_at") or 0),
        )


class BacktestAccumulator:
    def __init__(self, raw: dict[str, Any] | None = None) -> None:
        data = raw or load_backtest_state()
        self.cycles = int(data.get("cycles") or 0)
        self.best_sl_pct = float(data.get("best_sl_pct") or 0)
        self.best_tp_pct = float(data.get("best_tp_pct") or 0)
        self.updated_at = float(data.get("updated_at") or 0)
        self.symbols: dict[str, SymbolBacktestRecord] = {}
        for sym, row in (data.get("symbols") or {}).items():
            if isinstance(row, dict):
                self.symbols[str(sym).upper()] = SymbolBacktestRecord.from_dict(row)

    def save(self) -> None:
        save_backtest_state(
            {
                "cycles": self.cycles,
                "best_sl_pct": self.best_sl_pct,
                "best_tp_pct": self.best_tp_pct,
                "updated_at": self.updated_at,
                "symbols": {k: v.to_dict() for k, v in self.symbols.items()},
            }
        )

    def merge_record(self, rec: SymbolBacktestRecord) -> None:
        sym = rec.symbol.upper()
        if not sym:
            return
        prev = self.symbols.get(sym)
        if prev:
            rec.long = _merge_side(prev.long, rec.long)
            rec.short = _merge_side(prev.short, rec.short)
        self.symbols[sym] = rec

    def prune(self, max_symbols: int = 250) -> None:
        if len(self.symbols) <= max_symbols:
            return
        ordered = sorted(
            self.symbols.items(),
            key=lambda x: x[1].updated_at,
            reverse=True,
        )
        self.symbols = dict(ordered[:max_symbols])

    def best_global_params(
        self, default_sl: float, default_tp: float
    ) -> tuple[float, float]:
        if self.best_sl_pct > 0 and self.best_tp_pct > 0:
            return self.best_sl_pct, self.best_tp_pct
        return default_sl, default_tp

    def boost(self, symbol: str, side: str) -> float:
        """투자 제안·방향 분석 가중치 (0~22)."""
        rec = self.symbols.get(symbol.upper())
        if not rec:
            return 0.0
        st = rec.long if side == "long" else rec.short
        if st.trades < 1 or st.score < 35:
            return 0.0
        return min(22.0, st.score * 0.22)

    def top_symbols(self, side: str, limit: int = 20) -> list[tuple[str, SideStats]]:
        rows: list[tuple[str, SideStats]] = []
        for sym, rec in self.symbols.items():
            st = rec.long if side == "long" else rec.short
            if st.trades >= 1 and st.score >= 40:
                rows.append((sym, st))
        rows.sort(key=lambda x: (x[1].score, x[1].win_rate_pct), reverse=True)
        return rows[:limit]


def _merge_side(prev: SideStats, new: SideStats) -> SideStats:
    """누적 평균·합산."""
    t = prev.trades + new.trades
    if t <= 0:
        return new if new.trades else prev
    w = new.trades / t
    pw = prev.trades / t
    wins = prev.wins + new.wins
    losses = prev.losses + new.losses
    avg = prev.avg_return_pct * pw + new.avg_return_pct * w
    wr = (wins / t * 100) if t else 0.0
    # 점수는 최댓값만 쓰지 않고 EMA로 완만히 개선·악화 반영
    if new.trades > 0:
        score = prev.score * 0.65 + new.score * 0.35
    else:
        score = prev.score
    score = max(0.0, min(100.0, score))
    if new.score >= prev.score * 0.95 and new.best_sl_pct > 0:
        sl, tp = new.best_sl_pct, new.best_tp_pct
    else:
        sl, tp = prev.best_sl_pct, prev.best_tp_pct
    return SideStats(
        trades=t,
        wins=wins,
        losses=losses,
        avg_return_pct=avg,
        win_rate_pct=wr,
        best_sl_pct=sl,
        best_tp_pct=tp,
        score=score,
    )


def _score_side(wins: int, losses: int, rets: list[float], sl: float, tp: float) -> float:
    total = wins + losses
    if total < 1:
        return 0.0
    wr = wins / total
    avg = float(np.mean(rets)) if rets else 0.0
    # 기대값 성향 + 승률
    expectancy = wr * tp - (1 - wr) * sl
    raw = 40 + wr * 35 + avg * 2.5 + expectancy * 3
    return float(max(0, min(100, raw)))


def _simulate_side(
    closes: np.ndarray,
    *,
    side: str,
    sl_pct: float,
    tp_pct: float,
) -> tuple[int, int, list[float]]:
    """한 (sl,tp) 조합으로 단일 방향 시뮬."""
    sl = sl_pct / 100
    tp = tp_pct / 100
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    wins = losses = 0
    rets: list[float] = []

    for i in range(40, len(closes) - 8):
        if side == "long":
            if ema12[i] <= ema26[i] or closes[i] <= ema12[i]:
                continue
        else:
            if ema12[i] >= ema26[i] or closes[i] >= ema12[i]:
                continue
        entry = closes[i]
        outcome = None
        for j in range(i + 1, min(i + 36, len(closes))):
            if side == "long":
                pnl = (closes[j] - entry) / entry
            else:
                pnl = (entry - closes[j]) / entry
            if pnl <= -sl:
                outcome = pnl
                break
            if pnl >= tp:
                outcome = pnl
                break
        if outcome is None:
            continue
        rets.append(outcome * 100)
        if outcome >= 0:
            wins += 1
        else:
            losses += 1
        break
    return wins, losses, rets


def _optimize_side(closes: np.ndarray, side: str, base_sl: float, base_tp: float) -> SideStats:
    grid = list(PARAM_GRID)
    if (base_sl, base_tp) not in grid:
        grid.insert(0, (base_sl, base_tp))

    best = SideStats()
    for sl_p, tp_p in grid:
        w, l, rets = _simulate_side(closes, side=side, sl_pct=sl_p, tp_pct=tp_p)
        total = w + l
        if total < 1:
            continue
        sc = _score_side(w, l, rets, sl_p, tp_p)
        if sc > best.score:
            best = SideStats(
                trades=total,
                wins=w,
                losses=l,
                avg_return_pct=float(np.mean(rets)) if rets else 0.0,
                win_rate_pct=w / total * 100,
                best_sl_pct=sl_p,
                best_tp_pct=tp_p,
                score=sc,
            )
    return best


async def simulate_symbol(
    symbol: str,
    *,
    default_sl: float,
    default_tp: float,
) -> SymbolBacktestRecord | None:
    try:
        raw = await market.klines(symbol, "1h", 120)
    except Exception as e:
        logger.debug("bt klines %s: %s", symbol, e)
        return None
    if len(raw) < 65:
        return None
    closes = np.array([float(r[4]) for r in raw], dtype=float)
    long_st = _optimize_side(closes, "long", default_sl, default_tp)
    short_st = _optimize_side(closes, "short", default_sl, default_tp)
    if long_st.trades < 1 and short_st.trades < 1:
        return None
    return SymbolBacktestRecord(
        symbol=symbol.upper(),
        long=long_st,
        short=short_st,
        updated_at=time.time(),
    )


def _update_global_best(acc: BacktestAccumulator) -> None:
    sl_sum = tp_sum = wsum = 0.0
    for rec in acc.symbols.values():
        for st in (rec.long, rec.short):
            if st.trades < 1 or st.best_sl_pct <= 0:
                continue
            wt = st.trades * max(st.score, 1)
            sl_sum += st.best_sl_pct * wt
            tp_sum += st.best_tp_pct * wt
            wsum += wt
    if wsum > 0:
        acc.best_sl_pct = round(sl_sum / wsum, 2)
        acc.best_tp_pct = round(tp_sum / wsum, 2)


_cycle_offset = 0


def adaptive_batch_size(acc: BacktestAccumulator, base: int = 12) -> int:
    """데이터가 쌓일수록 한 주기에 더 많은 종목 분석."""
    from app.engine.backtest_learning import compute_data_maturity

    maturity = compute_data_maturity(acc) / 100.0
    return int(min(28, max(base, base + maturity * 16)))


async def run_accumulator_cycle(
    symbols: list[str],
    *,
    default_sl: float,
    default_tp: float,
    batch_size: int | None = None,
) -> tuple[BacktestAccumulator, int, int]:
    """심볼 배치 시뮬 → 파일 누적. 반환: (accumulator, tested, new_records)."""
    global _cycle_offset
    acc = BacktestAccumulator()
    if not symbols:
        return acc, 0, 0

    if batch_size is None:
        batch_size = adaptive_batch_size(acc)

    n = len(symbols)
    start = _cycle_offset % n
    _cycle_offset += 1
    batch: list[str] = []
    for i in range(batch_size):
        batch.append(symbols[(start + i) % n])

    preview = ", ".join(s.replace("USDT", "") for s in batch[:5])
    if len(batch) > 5:
        preview += f" 외 {len(batch) - 5}종"
    logger.info("[백테스트 배치] %s", preview)

    tested = 0
    updated = 0
    for sym in batch:
        rec = await simulate_symbol(sym, default_sl=default_sl, default_tp=default_tp)
        tested += 1
        if rec:
            acc.merge_record(rec)
            updated += 1

    acc.cycles += 1
    acc.updated_at = time.time()
    _update_global_best(acc)
    acc.prune(250)
    acc.save()
    from app.engine.backtest_learning import update_learning_from_batch

    update_learning_from_batch(acc, batch, default_sl=default_sl, default_tp=default_tp)
    return acc, tested, updated

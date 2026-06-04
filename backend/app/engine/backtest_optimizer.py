"""백테스트 누적·파라미터 탐색 → 롱/숏·투자 제안 가중치."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.config import settings
from app.engine.trading_fees import net_pnl_pct_after_fees
from app.market.upbit_data import market
from app.aidi_log import get_aidi_logger
from app.storage.persistence import load_backtest_state, save_backtest_state
from app.util.numbers import as_float

logger = get_aidi_logger()

# (손절%, 익절%) 후보 — 단타·스캘핑 중심 (수수료 제외 후 소폭 이익)
PARAM_GRID: list[tuple[float, float]] = [
    (1.8, 0.7),
    (2.2, 0.9),
    (2.6, 1.1),
    (3.0, 1.3),
    (3.5, 1.6),
    (4.0, 2.0),
    (5.0, 2.5),
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
            avg_return_pct=as_float(d.get("avg_return_pct")),
            win_rate_pct=as_float(d.get("win_rate_pct")),
            best_sl_pct=as_float(d.get("best_sl_pct")),
            best_tp_pct=as_float(d.get("best_tp_pct")),
            score=as_float(d.get("score")),
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
        self.best_sl_pct = as_float(data.get("best_sl_pct"))
        self.best_tp_pct = as_float(data.get("best_tp_pct"))
        self.updated_at = float(data.get("updated_at") or 0)
        self.symbols: dict[str, SymbolBacktestRecord] = {}
        for sym, row in (data.get("symbols") or {}).items():
            if isinstance(row, dict):
                self.symbols[str(sym).upper()] = SymbolBacktestRecord.from_dict(row)

    def save(self) -> None:
        raw = load_backtest_state()
        raw["cycles"] = self.cycles
        raw["best_sl_pct"] = self.best_sl_pct
        raw["best_tp_pct"] = self.best_tp_pct
        raw["updated_at"] = self.updated_at
        raw["symbols"] = {k: v.to_dict() for k, v in self.symbols.items()}
        save_backtest_state(raw)

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
        sl = as_float(self.best_sl_pct)
        tp = as_float(self.best_tp_pct)
        d_sl = as_float(default_sl, 3.0)
        d_tp = as_float(default_tp, 5.0)
        if sl > 0 and tp > 0:
            return sl, tp
        return d_sl, d_tp

    def boost(self, symbol: str, side: str) -> float:
        """투자 제안·방향 분석 가중치 (0~22)."""
        rec = self.symbols.get(symbol.upper())
        if not rec:
            return 0.0
        st = rec.long if side == "long" else rec.short
        if st.trades < 1 or as_float(st.score) < 35:
            return 0.0
        return min(22.0, as_float(st.score) * 0.22)

    def top_symbols(self, side: str, limit: int = 20) -> list[tuple[str, SideStats]]:
        rows: list[tuple[str, SideStats]] = []
        for sym, rec in self.symbols.items():
            st = rec.long if side == "long" else rec.short
            if st.trades >= 1 and st.score >= 40:
                rows.append((sym, st))
        rows.sort(key=lambda x: (as_float(x[1].score), as_float(x[1].win_rate_pct)), reverse=True)
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
    prev_score = as_float(prev.score)
    new_score = as_float(new.score)
    if new.trades > 0:
        score = prev_score * 0.65 + new_score * 0.35
    else:
        score = prev_score
    score = max(0.0, min(100.0, score))
    if new_score >= prev_score * 0.95 and as_float(new.best_sl_pct) > 0:
        sl, tp = as_float(new.best_sl_pct), as_float(new.best_tp_pct)
    else:
        sl, tp = as_float(prev.best_sl_pct), as_float(prev.best_tp_pct)
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
    loss_penalty = max(0.0, 0.48 - wr) * 45
    raw = 38 + wr * 42 + avg * 3.0 + expectancy * 4 - loss_penalty
    return float(max(0, min(100, raw)))


def _rsi_at(closes: np.ndarray, idx: int, period: int = 14) -> float:
    if idx < period:
        return 50.0
    window = closes[idx - period : idx + 1]
    deltas = np.diff(window)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(gains.mean()) or 1e-9
    avg_loss = float(losses.mean()) or 1e-9
    return float(100 - (100 / (1 + avg_gain / avg_loss)))


def _entry_allowed(
    closes: np.ndarray,
    volumes: np.ndarray,
    ema12: np.ndarray,
    ema26: np.ndarray,
    i: int,
    side: str,
) -> bool:
    price = closes[i]
    if price <= 0 or ema12[i] <= 0 or ema26[i] <= 0:
        return False

    rsi = _rsi_at(closes, i)
    dist_ema12 = (price - ema12[i]) / ema12[i] * 100
    recent_24 = (
        (price - closes[i - 24]) / closes[i - 24] * 100
        if i >= 24 and closes[i - 24] > 0
        else 0.0
    )
    recent_8 = (
        (price - closes[i - 8]) / closes[i - 8] * 100
        if i >= 8 and closes[i - 8] > 0
        else 0.0
    )
    last3 = (
        (price - closes[i - 3]) / closes[i - 3] * 100
        if i >= 3 and closes[i - 3] > 0
        else 0.0
    )
    avg_vol = float(volumes[max(0, i - 30) : i].mean()) if i > 5 else 0.0
    vol_ok = not avg_vol or volumes[i] >= avg_vol * 0.75

    if side == "long":
        if ema12[i] <= ema26[i] or price <= ema12[i]:
            return False
        if rsi >= 76 or dist_ema12 > 3.8:
            return False
        if recent_24 > 12.0 and last3 < -1.2:
            return False
        if recent_8 > 7.5 and not vol_ok:
            return False
        return True

    if ema12[i] >= ema26[i] or price >= ema12[i]:
        return False
    if rsi <= 24 or dist_ema12 < -3.8:
        return False
    if recent_24 < -12.0 and last3 > 1.2:
        return False
    if recent_8 < -7.5 and not vol_ok:
        return False
    return True


def _simulate_side(
    closes: np.ndarray,
    *,
    side: str,
    sl_pct: float,
    tp_pct: float,
    fee_pct: float = 0.05,
    highs: np.ndarray | None = None,
    lows: np.ndarray | None = None,
    volumes: np.ndarray | None = None,
) -> tuple[int, int, list[float]]:
    """한 (sl,tp) 조합으로 단일 방향 시뮬."""
    sl = sl_pct / 100
    tp = tp_pct / 100
    highs = highs if highs is not None and len(highs) == len(closes) else closes
    lows = lows if lows is not None and len(lows) == len(closes) else closes
    volumes = (
        volumes
        if volumes is not None and len(volumes) == len(closes)
        else np.ones_like(closes)
    )
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    wins = losses = 0
    rets: list[float] = []

    i = 40
    while i < len(closes) - 8:
        if not _entry_allowed(closes, volumes, ema12, ema26, i, side):
            i += 1
            continue
        entry = closes[i]
        outcome = None
        for j in range(i + 1, min(i + 36, len(closes))):
            if side == "long":
                hit_sl = (lows[j] - entry) / entry <= -sl
                hit_tp = (highs[j] - entry) / entry >= tp
                close_pnl = (closes[j] - entry) / entry
            else:
                hit_sl = (entry - highs[j]) / entry <= -sl
                hit_tp = (entry - lows[j]) / entry >= tp
                close_pnl = (entry - closes[j]) / entry
            if hit_sl and hit_tp:
                outcome = -sl
                break
            if hit_sl:
                outcome = -sl
                break
            if hit_tp:
                outcome = tp
                break
            if j == min(i + 36, len(closes)) - 1 and abs(close_pnl) >= tp * 0.7:
                outcome = close_pnl
        if outcome is None:
            i += 1
            continue
        net_pct = net_pnl_pct_after_fees(outcome * 100, fee_pct)
        rets.append(net_pct)
        if net_pct >= 0:
            wins += 1
        else:
            losses += 1
        i += 12
    return wins, losses, rets


def _optimize_side(
    closes: np.ndarray,
    side: str,
    base_sl: float,
    base_tp: float,
    *,
    fee_pct: float = 0.05,
) -> SideStats:
    grid = list(PARAM_GRID)
    if (base_sl, base_tp) not in grid:
        grid.insert(0, (base_sl, base_tp))

    best = SideStats()
    for sl_p, tp_p in grid:
        w, l, rets = _simulate_side(
            closes, side=side, sl_pct=sl_p, tp_pct=tp_p, fee_pct=fee_pct
        )
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


def _optimize_side_with_ohlcv(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    volumes: np.ndarray,
    side: str,
    base_sl: float,
    base_tp: float,
    *,
    fee_pct: float = 0.05,
) -> SideStats:
    grid = list(PARAM_GRID)
    if (base_sl, base_tp) not in grid:
        grid.insert(0, (base_sl, base_tp))

    best = SideStats()
    for sl_p, tp_p in grid:
        w, l, rets = _simulate_side(
            closes,
            side=side,
            sl_pct=sl_p,
            tp_pct=tp_p,
            fee_pct=fee_pct,
            highs=highs,
            lows=lows,
            volumes=volumes,
        )
        total = w + l
        if total < 2:
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
    fee_pct: float = 0.05,
) -> SymbolBacktestRecord | None:
    try:
        raw_15m = await market.klines(symbol, "15m", 192)
        raw_1h = await market.klines(symbol, "1h", 120)
    except Exception as e:
        logger.debug("bt klines %s: %s", symbol, e)
        return None
    raw = raw_15m if len(raw_15m) >= 80 else raw_1h
    if len(raw) < 65:
        return None
    closes = np.array([float(r[4]) for r in raw], dtype=float)
    highs = np.array([float(r[2]) for r in raw], dtype=float)
    lows = np.array([float(r[3]) for r in raw], dtype=float)
    volumes = np.array([float(r[5]) for r in raw], dtype=float)
    long_st = _optimize_side_with_ohlcv(
        closes, highs, lows, volumes, "long", default_sl, default_tp, fee_pct=fee_pct
    )
    short_st = _optimize_side_with_ohlcv(
        closes, highs, lows, volumes, "short", default_sl, default_tp, fee_pct=fee_pct
    )
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
    fee_pct: float = 0.05,
) -> tuple[BacktestAccumulator, int, int, list[str]]:
    """심볼 배치 시뮬 → 파일 누적. 반환: (accumulator, tested, updated, batch)."""
    global _cycle_offset
    acc = BacktestAccumulator()
    if not symbols:
        return acc, 0, 0, []

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
        rec = await simulate_symbol(
            sym, default_sl=default_sl, default_tp=default_tp, fee_pct=fee_pct
        )
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
    return acc, tested, updated, batch

"""기존 보유 포지션 — 진입 유형(롱/단타)에 맞게 손익절 % 재적용."""

from __future__ import annotations

from app.engine.backtest_learning import load_learning_state, resolve_sl_tp_from_backtest
from app.engine.backtest_optimizer import BacktestAccumulator
from app.engine.backtest_runner import get_accumulator
from app.engine.trade_feedback import _mode_from_outlook
from app.models import AppConfig, Position


def exit_mode_for_position(pos: Position) -> str:
    mode = _mode_from_outlook(pos.entry_outlook or "")
    if mode in ("long", "scalp"):
        return mode
    text = f"{pos.entry_outlook or ''} {pos.entry_reason or ''}".lower()
    if "단타" in text or "scalp" in text:
        return "scalp"
    return "long"


def migrate_position_exit(
    pos: Position,
    config: AppConfig,
    *,
    acc: BacktestAccumulator | None = None,
    force: bool = False,
) -> tuple[bool, str]:
    """auto_quantity 보유 — auto_exit_* 및 손익절 가격 갱신."""
    if pos.auto_quantity <= 1e-12:
        return False, "AI 수량 없음"
    if pos.custom_sl_tp and not force:
        return False, "수동 손익절 지정 중"

    had = float(getattr(pos, "auto_exit_sl_pct", 0) or 0) > 0
    if had and not force:
        return False, "이미 진입 유형 손익절 적용됨"

    mode = exit_mode_for_position(pos)
    acc = acc or get_accumulator()
    learning = load_learning_state()
    sl_p, tp_p, src = resolve_sl_tp_from_backtest(
        acc,
        learning,
        pos.symbol,
        mode=mode,
        default_sl=config.stop_loss_pct,
        default_tp=config.take_profit_pct,
    )
    entry = pos.auto_avg_price or pos.avg_price
    if entry <= 0:
        entry = pos.current_price
    if entry <= 0:
        return False, "평단가 없음"

    sl_ratio = sl_p / 100.0
    tp_ratio = tp_p / 100.0
    pos.auto_exit_sl_pct = round(sl_p, 4)
    pos.auto_exit_tp_pct = round(tp_p, 4)
    pos.stop_loss = entry * (1 - sl_ratio)
    pos.take_profit = entry * (1 + tp_ratio)
    if pos.trailing_high <= 0:
        pos.trailing_high = max(pos.current_price, entry)

    label = f"{mode} · {src} · 손절{sl_p:g}%/익절{tp_p:g}%"
    return True, label


def migrate_all_positions(
    portfolio,
    config: AppConfig,
    *,
    force: bool = False,
) -> tuple[int, list[str]]:
    acc = get_accumulator()
    n = 0
    lines: list[str] = []
    for sym, pos in list(portfolio.positions.items()):
        ok, msg = migrate_position_exit(pos, config, acc=acc, force=force)
        if ok:
            n += 1
            lines.append(f"{pos.display}: {msg}")
    return n, lines

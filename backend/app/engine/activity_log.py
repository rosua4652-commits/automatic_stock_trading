"""Bot activity timeline for UI (scan / BT / auto-invest steps)."""

from __future__ import annotations

import time

from app.models import ActivityEntry, BotState


def push_activity(
    bot: BotState,
    phase: str,
    message: str,
    *,
    level: str = "info",
    max_items: int = 48,
) -> None:
    entry = ActivityEntry(
        ts=time.time(),
        phase=phase,
        level=level,
        message=message,
    )
    bot.activity_log = [entry, *bot.activity_log][:max_items]


def set_phase(bot: BotState, phase: str, detail: str = "") -> None:
    bot.phase = phase
    if detail:
        bot.phase_detail = detail

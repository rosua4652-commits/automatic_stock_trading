"""자동 매수 허용 시간대 (KST)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import AppConfig

KST = timezone(timedelta(hours=9))


def auto_buy_window_open(config: AppConfig) -> tuple[bool, str]:
    if not getattr(config, "trade_hours_enabled", False):
        return True, ""
    now = datetime.now(KST)
    hour = now.hour
    start = int(getattr(config, "trade_start_hour_kst", 8) or 8)
    end = int(getattr(config, "trade_end_hour_kst", 23) or 23)
    start = max(0, min(23, start))
    end = max(0, min(24, end))

    if start == end:
        return True, ""

    if start < end:
        ok = start <= hour < end
    else:
        ok = hour >= start or hour < end

    if ok:
        return True, ""
    return (
        False,
        f"매수 시간 외 (KST {start:02d}~{end:02d}시, 현재 {hour:02d}시) — 스캔만 계속",
    )

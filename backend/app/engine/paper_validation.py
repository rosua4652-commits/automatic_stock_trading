"""모의 자동투자 검증 일수 — 실거래 자동투자 오픈 게이트."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))
FILE = Path(__file__).resolve().parent.parent.parent / "data" / "paper_auto_days.json"


def _today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _load() -> dict[str, Any]:
    if not FILE.is_file():
        return {"dates": []}
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"dates": []}


def _save(data: dict[str, Any]) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record_paper_auto_day() -> None:
    data = _load()
    dates = list(data.get("dates") or [])
    today = _today()
    if today not in dates:
        dates.append(today)
        dates.sort()
        data["dates"] = dates[-120:]
        data["updated_at"] = time.time()
        _save(data)


def paper_auto_days_count() -> int:
    return len(_load().get("dates") or [])


def check_paper_validation_for_live(
    config,
    *,
    is_paper: bool,
) -> tuple[bool, str]:
    """실거래 자동투자 전 모의 검증 일수."""
    if is_paper:
        return True, ""
    need = int(getattr(config, "paper_days_before_live_auto", 3) or 3)
    if need <= 0:
        return True, ""
    if getattr(config, "allow_live_auto_invest", False):
        return True, ""
    got = paper_auto_days_count()
    if got >= need:
        return (
            True,
            f"모의 검증 {got}일 (기준 {need}일) — 설정에서 실거래 자동투자 허용 가능",
        )
    return (
        False,
        f"실거래 자동투자: 모의 자동투자 {got}/{need}일 "
        f"(모의에서 자동투자 {need}일 이상 후 설정 허용)",
    )

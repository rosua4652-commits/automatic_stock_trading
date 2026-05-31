"""업비트 API 상태 — UI 스캔 일시 중지 메시지."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class MarketHealthState:
    status: str = "ok"  # ok | rate_limit | maintenance | error
    detail: str = ""
    updated_at: float = 0.0
    retry_after_sec: float = 0.0

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "detail": self.detail,
            "updated_at": self.updated_at,
            "retry_after_sec": round(self.retry_after_sec, 1),
        }


_state = MarketHealthState()


def get_market_health() -> MarketHealthState:
    return _state


def report_market_ok() -> None:
    global _state
    if _state.status == "ok":
        return
    _state = MarketHealthState(status="ok", updated_at=time.time())


def report_rate_limit(detail: str = "", retry_sec: float = 30.0) -> None:
    global _state
    _state = MarketHealthState(
        status="rate_limit",
        detail=detail or "업비트 요청 제한 (429)",
        updated_at=time.time(),
        retry_after_sec=retry_sec,
    )


def report_market_error(detail: str) -> None:
    global _state
    low = (detail or "").lower()
    st = "maintenance" if "점검" in detail or "maintenance" in low else "error"
    _state = MarketHealthState(
        status=st,
        detail=detail[:200],
        updated_at=time.time(),
        retry_after_sec=60.0,
    )

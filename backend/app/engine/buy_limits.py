"""건당 최소 매수 금액 — 업비트 하한 + 사용자 설정."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import settings
from app.util.numbers import as_float

if TYPE_CHECKING:
    from app.models import AppConfig

# 업비트 KRW 시장가 매수·매도 공통 하한
UPBIT_MIN_ORDER_KRW = 5_000.0


def effective_min_buy_krw(config: AppConfig | None = None) -> float:
    """자동투자·승인 매수 — 설정값과 업비트 하한(5,000원) 중 큰 값."""
    raw = as_float(getattr(config, "min_buy_krw", 0), 0.0) if config else 0.0
    if raw <= 0:
        raw = as_float(getattr(settings, "min_buy_krw", 0), 0.0)
    if raw <= 0:
        raw = 6_000.0
    return max(UPBIT_MIN_ORDER_KRW, raw)


def manual_min_buy_krw() -> float:
    """수동 지정 매수 — 업비트 주문 하한만 적용."""
    return UPBIT_MIN_ORDER_KRW

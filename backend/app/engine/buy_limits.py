"""건당 최소 매수 금액 — 업비트 하한 + 사용자 설정."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from app.models import AppConfig

# 업비트 KRW 시장가 매수·매도 공통 하한
UPBIT_MIN_ORDER_KRW = 5_000.0


def effective_min_buy_krw(config: AppConfig | None = None) -> float:
    """설정값과 업비트 하한(5,000원) 중 큰 값."""
    raw = float(getattr(config, "min_buy_krw", 0) or 0) if config else 0.0
    if raw <= 0:
        raw = float(getattr(settings, "min_buy_krw", UPBIT_MIN_ORDER_KRW) or UPBIT_MIN_ORDER_KRW)
    return max(UPBIT_MIN_ORDER_KRW, raw)

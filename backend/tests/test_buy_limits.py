"""최소 매수 금액 설정."""

from app.engine.buy_limits import UPBIT_MIN_ORDER_KRW, effective_min_buy_krw
from app.models import AppConfig


def test_effective_min_buy_at_upbit_floor():
    cfg = AppConfig(min_buy_krw=5_000)
    assert effective_min_buy_krw(cfg) == UPBIT_MIN_ORDER_KRW


def test_effective_min_buy_user_setting():
    cfg = AppConfig(min_buy_krw=20_000)
    assert effective_min_buy_krw(cfg) == 20_000

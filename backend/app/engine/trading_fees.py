"""거래 수수료 — 설정 trading_fee_pct(기본 0.05% 편도) 공통 계산."""

from __future__ import annotations


def fee_rate(fee_pct: float) -> float:
    return max(0.0, float(fee_pct or 0)) / 100.0


def round_trip_fee_pct(fee_pct: float) -> float:
    """왕복 수수료 % (매수 편도 + 매도 편도)."""
    return float(fee_pct or 0) * 2.0


def cash_required_for_buy(principal_krw: float, fee_pct: float) -> float:
    """매수 원금 + 편도 수수료에 필요한 현금."""
    return principal_krw * (1.0 + fee_rate(fee_pct))


def deployable_cash_krw(cash_krw: float, fee_pct: float = 0.05) -> float:
    """
    AI 배분·자동매수에 쓸 수 있는 **매수 원금** 상한.
    - 매수: 원금 × (1 + fee)
    - 매도 시 편도 수수료 여유: 추가 × (1 + fee)
  """
    r = fee_rate(fee_pct)
    if cash_krw <= 0:
        return 0.0
    round_trip = (1.0 + r) ** 2
    return max(0.0, cash_krw / round_trip * 0.98)


def cap_principal_to_cash(
    principal_total: float,
    cash_krw: float,
    fee_pct: float,
) -> float:
    """원금 합계가 현금(수수료 포함)을 넘지 않도록 상한."""
    if principal_total <= 0:
        return 0.0
    max_principal = deployable_cash_krw(cash_krw, fee_pct)
    return min(principal_total, max_principal)


def net_pnl_pct_after_fees(gross_return_pct: float, fee_pct: float) -> float:
    """가격 수익률(%)에서 왕복 수수료(%) 차감."""
    return gross_return_pct - round_trip_fee_pct(fee_pct)


def fee_krw_round_trip(principal_krw: float, fee_pct: float) -> float:
    """원금 기준 왕복 수수료 원화 (근사)."""
    r = fee_rate(fee_pct)
    return principal_krw * r * 2.0

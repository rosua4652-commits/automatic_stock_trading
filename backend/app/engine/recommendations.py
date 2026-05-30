"""AI 투자 제안: 비중·금액 산출 (자동 체결 없음)."""

from app.config import settings
from app.models import AppConfig, CoinCandidate, InvestmentRecommendation

MIN_BUY = settings.min_buy_krw


def build_recommendations(
    candidates: list[CoinCandidate],
    cash_krw: float,
    config: AppConfig,
    held_symbols: set[str],
) -> list[InvestmentRecommendation]:
    """진입 가능 후보에 투자 가능 현금을 점수 비중으로 배분."""
    budget = cash_krw * 0.85
    if budget < MIN_BUY:
        return []

    pool: list[CoinCandidate] = []
    for c in candidates:
        if c.symbol in held_symbols:
            continue
        if not c.entry_ok:
            continue
        if c.score < config.min_buy_score:
            continue
        pool.append(c)

    pool.sort(key=lambda c: (c.entry_score + c.score), reverse=True)
    pool = pool[:15]
    if not pool:
        return []

    weights: list[float] = []
    for c in pool:
        w = max(1.0, c.score + c.entry_score)
        weights.append(w)
    total_w = sum(weights)

    recs: list[InvestmentRecommendation] = []
    allocated = 0.0
    for c, w in zip(pool, weights):
        amount = round(budget * (w / total_w), -3)  # 1,000원 단위
        if amount < MIN_BUY:
            continue
        weight_pct = round(w / total_w * 100, 1)
        allocated += amount
        recs.append(
            InvestmentRecommendation(
                symbol=c.symbol,
                base=c.base,
                name_ko=c.name_ko,
                display=c.display,
                pair_label=c.pair_label,
                market_score=c.score,
                entry_score=c.entry_score,
                weight_pct=weight_pct,
                amount_krw=amount,
                entry_detail=c.entry_detail or c.entry_outlook,
                change_24h=c.change_24h,
                trend=c.trend,
                selected=True,
            )
        )

  # 예산 초과 시 비례 축소
    if allocated > budget and recs:
        scale = budget / allocated
        recs = [
            r.model_copy(
                update={"amount_krw": max(MIN_BUY, round(r.amount_krw * scale, -3))}
            )
            for r in recs
        ]
    return recs

"""AI 투자 제안: 비중·금액 산출."""

from app.config import settings
from app.engine.trading_fees import (
    cash_required_for_buy,
    deployable_cash_krw,
    fee_krw_round_trip,
)
from app.engine.scalp_filters import scalp_market_fit
from app.engine.backtest_learning import (
    format_sl_tp_label,
    load_learning_state,
    resolve_sl_tp_from_backtest,
    symbol_passes_learning,
)
from app.engine.backtest_optimizer import BacktestAccumulator
from app.models import AppConfig, CoinCandidate, InvestmentRecommendation

MIN_BUY = settings.min_buy_krw


def _tier_to_mode(tier: str) -> str:
    return "scalp" if (tier or "").lower() == "scalp" else "long"


def _bt_line_for_symbol(
    acc: BacktestAccumulator,
    symbol: str,
    *,
    tier: str,
) -> str:
    learning = load_learning_state()
    mode = _tier_to_mode(tier)
    rec = acc.symbols.get(symbol.upper())
    st = None
    if rec:
        st = rec.long if mode == "long" else rec.short
    floor = (
        learning.long_min_bt_score
        if mode == "long"
        else learning.scalp_min_bt_score
    )
    if st and st.trades >= 1:
        return (
            f"BT {st.score:.0f}점 (기준≥{floor:.0f}) · 승률 {st.win_rate_pct:.0f}% · "
            f"{st.trades}건"
        )
    return f"BT 누적 중 · 기준≥{floor:.0f} · 성숙 {learning.data_maturity_pct:.0f}%"


def _entry_detail_with_backtest(
    c: CoinCandidate,
    backtest,
    *,
    tier: str,
    sl_pct: float,
    tp_pct: float,
    sl_source: str,
    default_sl: float,
    default_tp: float,
) -> str:
    base = c.entry_detail or c.entry_outlook or ""
    sl_line = format_sl_tp_label(sl_pct, tp_pct, sl_source)
    if backtest is None:
        return f"{base} · {sl_line}" if base else sl_line
    rec = backtest.symbols.get(c.symbol.upper())
    mode = _tier_to_mode(tier)
    st = None
    if rec:
        st = rec.long if mode == "long" else rec.short
    if st and st.trades >= 1:
        bt = (
            f"BT {st.score:.0f}점 · 승률 {st.win_rate_pct:.0f}% · "
            f"{st.trades}건 · {sl_line}"
        )
        return f"{base} · {bt}" if base else bt
    return f"{base} · {sl_line}" if base else sl_line


def _trade_plan(
    amount_krw: float,
    price_usdt: float,
    usdt_krw: float,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> tuple[float, float, float, float, float]:
    """매수가·수량 기준 예상 손절/익절 가격(USDT) 및 원화 손익."""
    if price_usdt <= 0 or usdt_krw <= 0 or amount_krw <= 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    sl_r = stop_loss_pct / 100
    tp_r = take_profit_pct / 100
    sl_price = price_usdt * (1 - sl_r)
    tp_price = price_usdt * (1 + tp_r)
    qty = amount_krw / (price_usdt * usdt_krw)
    sl_krw = max(0.0, (price_usdt - sl_price) * qty * usdt_krw)
    tp_krw = max(0.0, (tp_price - price_usdt) * qty * usdt_krw)
    return round(qty, 6), sl_price, tp_price, round(sl_krw, 0), round(tp_krw, 0)


def _trade_plan_with_fees(
    amount_krw: float,
    price_usdt: float,
    usdt_krw: float,
    stop_loss_pct: float,
    take_profit_pct: float,
    fee_pct: float,
) -> tuple[float, float, float, float, float]:
    qty, sl_price, tp_price, sl_krw, tp_krw = _trade_plan(
        amount_krw, price_usdt, usdt_krw, stop_loss_pct, take_profit_pct
    )
    fees = fee_krw_round_trip(amount_krw, fee_pct)
    sl_krw = max(0.0, sl_krw + fees)
    tp_krw = max(0.0, tp_krw - fees)
    return qty, sl_price, tp_price, round(sl_krw, 0), round(tp_krw, 0)


def allocate_amounts_by_weights(
    weights: list[float],
    cash_krw: float,
    fee_pct: float = 0.05,
) -> list[float]:
    """
    점수 비중으로 현금 배분. 합계 <= deployable cash, 각 건 MIN_BUY 이상(또는 0).
    """
    if not weights or cash_krw < MIN_BUY:
        return [0.0] * len(weights)

    budget = round(deployable_cash_krw(cash_krw, fee_pct), -3)
    if budget < MIN_BUY:
        return [0.0] * len(weights)

    n = len(weights)
    max_slots = min(n, int(budget // MIN_BUY))
    if max_slots <= 0:
        return [0.0] * n

    order = sorted(range(n), key=lambda i: weights[i], reverse=True)[:max_slots]
    sel_w = [weights[i] for i in order]
    wsum = sum(sel_w)
    if wsum <= 0:
        return [0.0] * n

    amts: list[float] = []
    for w in sel_w:
        amts.append(max(MIN_BUY, round(budget * w / wsum, -3)))

    def _trim() -> None:
        nonlocal amts, order, sel_w
        while sum(amts) > budget and len(amts) > 1:
            amts.pop()
            order = order[: len(amts)]
            sel_w = sel_w[: len(amts)]
            wsum = sum(sel_w)
            amts = [max(MIN_BUY, round(budget * w / wsum, -3)) for w in sel_w]

        while sum(amts) > budget and amts:
            over = sum(amts) - budget
            i = max(range(len(amts)), key=lambda j: amts[j])
            cut = min(over, amts[i] - MIN_BUY)
            if cut < 1000:
                if len(amts) > 1:
                    amts.pop(i)
                    order.pop(i)
                    sel_w.pop(i)
                    wsum = sum(sel_w) or 1
                    amts = [max(MIN_BUY, round(budget * w / wsum, -3)) for w in sel_w]
                else:
                    amts[i] = max(MIN_BUY, budget)
                    break
            else:
                amts[i] = round(amts[i] - cut, -3)

    _trim()

    out = [0.0] * n
    for idx, a in zip(order, amts):
        if a >= MIN_BUY:
            out[idx] = a

    while sum(out) > budget:
        active = [i for i in range(n) if out[i] >= MIN_BUY]
        if not active:
            break
        i = max(active, key=lambda j: out[j])
        over = sum(out) - budget
        if out[i] - max(MIN_BUY, over) >= MIN_BUY:
            out[i] = round(out[i] - max(over, 1000), -3)
        elif len(active) > 1:
            out[i] = 0.0
        else:
            out[i] = round(budget, -3)
            break
    return out


def cap_apply_amounts(
    amounts: dict[str, float],
    cash_krw: float,
    fee_pct: float = 0.05,
) -> dict[str, float]:
    """승인 매수 합계가 현금을 넘지 않도록 비례 축소."""
    if not amounts:
        return amounts
    budget = deployable_cash_krw(cash_krw, fee_pct)
    total = sum(amounts.values())
    if total <= budget:
        out = {k: max(MIN_BUY, round(v, -3)) for k, v in amounts.items() if v >= MIN_BUY}
    else:
        keys = list(amounts.keys())
        weights = [amounts[k] for k in keys]
        scaled = allocate_amounts_by_weights(weights, cash_krw, fee_pct)
        out = {k: scaled[i] for i, k in enumerate(keys) if scaled[i] >= MIN_BUY}

    # 매수 원금 + 편도 수수료 합이 현금을 넘지 않도록 최종 검증
    principal_sum = sum(out.values())
    need = cash_required_for_buy(principal_sum, fee_pct)
    if need > cash_krw and principal_sum > 0:
        scale = deployable_cash_krw(cash_krw, fee_pct) / principal_sum
        out = {
            k: max(MIN_BUY, round(v * scale, -3))
            for k, v in out.items()
            if v * scale >= MIN_BUY
        }
    return out


def build_recommendations(
    candidates: list[CoinCandidate],
    cash_krw: float,
    config: AppConfig,
    held_symbols: set[str],
    *,
    tickers: dict | None = None,
    usdt_krw: float = 1350.0,
    backtest=None,
) -> list[InvestmentRecommendation]:
    """진입 가능 후보에 보유 현금 범위 내에서 점수 비중 배분."""
    fee_pct = float(getattr(config, "trading_fee_pct", 0.05))
    budget = deployable_cash_krw(cash_krw, fee_pct)
    if budget < MIN_BUY:
        return []

    pool: list[CoinCandidate] = []
    entry_floor = config.min_entry_score * 0.85
    for c in candidates:
        if c.symbol in held_symbols:
            continue
        if c.score < config.min_buy_score:
            continue
        if c.entry_ok or getattr(c, "entry_scalp_ok", False):
            pool.append(c)
            continue
        if c.entry_score >= entry_floor:
            pool.append(c)

    def _rank(c: CoinCandidate) -> float:
        base = c.entry_score + c.score
        if backtest is not None:
            base += backtest.boost(c.symbol, "long")
        return base

    pool.sort(key=_rank, reverse=True)
    pool = pool[:15]
    if not pool:
        return []

    acc = (
        backtest
        if isinstance(backtest, BacktestAccumulator)
        else BacktestAccumulator()
    )
    learning = load_learning_state()

    weights = [max(1.0, _rank(c)) for c in pool]
    amounts = allocate_amounts_by_weights(weights, cash_krw, fee_pct)
    total_allocated = sum(amounts)

    recs: list[InvestmentRecommendation] = []
    for c, amount, w in zip(pool, amounts, weights):
        if amount < MIN_BUY:
            continue
        weight_pct = (
            round(amount / total_allocated * 100, 1) if total_allocated > 0 else 0.0
        )
        price_usdt = 0.0
        qty_est = 0.0
        tier = (
            "auto"
            if c.entry_ok
            else ("scalp" if getattr(c, "entry_scalp_ok", False) else "watch")
        )
        mode = _tier_to_mode(tier)
        sl_use, tp_use, sl_src = resolve_sl_tp_from_backtest(
            acc,
            learning,
            c.symbol,
            mode=mode,
            default_sl=config.stop_loss_pct,
            default_tp=config.take_profit_pct,
        )

        sl_price = tp_price = sl_krw = tp_krw = 0.0
        if tickers and c.symbol in tickers:
            price_usdt = float(tickers[c.symbol].get("lastPrice") or 0)
            if price_usdt > 0 and usdt_krw > 0:
                qty_est, sl_price, tp_price, sl_krw, tp_krw = _trade_plan_with_fees(
                    amount,
                    price_usdt,
                    usdt_krw,
                    sl_use,
                    tp_use,
                    fee_pct,
                )
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
                price_usdt=price_usdt,
                quantity_est=qty_est,
                stop_loss_price_usdt=sl_price,
                take_profit_price_usdt=tp_price,
                stop_loss_krw=sl_krw,
                take_profit_krw=tp_krw,
                stop_loss_pct=sl_use,
                take_profit_pct=tp_use,
                sl_tp_source=sl_src,
                entry_tier=tier,
                entry_detail=_entry_detail_with_backtest(
                    c,
                    acc,
                    tier=tier,
                    sl_pct=sl_use,
                    tp_pct=tp_use,
                    sl_source=sl_src,
                    default_sl=config.stop_loss_pct,
                    default_tp=config.take_profit_pct,
                ),
                bt_line=_bt_line_for_symbol(acc, c.symbol, tier=tier),
                change_24h=c.change_24h,
                volume_usdt=float(getattr(c, "volume_usdt", 0) or 0),
                trend=c.trend,
                selected=True,
            )
        )
    return recs


def filter_recommendations_for_auto(
    recs: list[InvestmentRecommendation],
    *,
    auto_long: bool,
    auto_scalp: bool,
    acc: BacktestAccumulator | None,
    max_picks: int,
    flash_block_until: dict[str, float] | None = None,
    paper_relax_bt: bool = False,
) -> list[InvestmentRecommendation]:
    """롱·단타·혼합 — 학습 임계값 통과한 제안만."""
    if not recs or max_picks <= 0:
        return []
    if not auto_long and not auto_scalp:
        return []

    learning = load_learning_state()
    acc = acc or BacktestAccumulator()
    from app.engine.flash_crash_guard import is_symbol_flash_blocked

    long_pool: list[InvestmentRecommendation] = []
    scalp_pool: list[InvestmentRecommendation] = []
    for r in recs:
        if flash_block_until and is_symbol_flash_blocked(flash_block_until, r.symbol):
            continue
        tier = (r.entry_tier or "").lower()
        if auto_long and tier == "auto":
            ok, _ = symbol_passes_learning(
                acc, learning, r.symbol, mode="long", paper_relax=paper_relax_bt
            )
            if ok:
                long_pool.append(r)
        elif auto_scalp and tier == "scalp":
            liq_ok, _ = scalp_market_fit(
                volume_usdt=float(getattr(r, "volume_usdt", 0) or 0),
                change_24h=float(getattr(r, "change_24h", 0) or 0),
            )
            if not liq_ok:
                continue
            ok, _ = symbol_passes_learning(
                acc, learning, r.symbol, mode="scalp", paper_relax=paper_relax_bt
            )
            if ok:
                scalp_pool.append(r)

    long_pool.sort(key=lambda x: x.entry_score + x.market_score, reverse=True)
    scalp_pool.sort(key=lambda x: x.entry_score + x.market_score, reverse=True)

    picks: list[InvestmentRecommendation] = []
    if auto_long and auto_scalp:
        li, si = 0, 0
        while len(picks) < max_picks and (li < len(long_pool) or si < len(scalp_pool)):
            if li < len(long_pool) and len(picks) < max_picks:
                picks.append(long_pool[li])
                li += 1
            if si < len(scalp_pool) and len(picks) < max_picks:
                picks.append(scalp_pool[si])
                si += 1
            if li >= len(long_pool) and si >= len(scalp_pool):
                break
    elif auto_long:
        picks = long_pool[:max_picks]
    else:
        picks = scalp_pool[:max_picks]
    return picks

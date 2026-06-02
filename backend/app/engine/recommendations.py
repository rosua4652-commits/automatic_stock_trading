"""AI 투자 제안: 비중·금액 산출."""

import math

from app.engine.buy_limits import UPBIT_MIN_ORDER_KRW, effective_min_buy_krw
from app.engine.trading_fees import (
    cash_required_for_buy,
    deployable_cash_krw,
    fee_krw_round_trip,
)
from app.engine.scalp_filters import scalp_market_fit
from app.engine.surge_classifier import classify_moonshot
from app.engine.news_signals import NewsSymbolScore, is_news_surge
from app.engine.surge_tag_expiry import (
    effective_is_news_surge,
    effective_news_score_for_moonshot,
)
from app.engine.exit_strength import strength_default_sl_tp
from app.engine.backtest_learning import (
    format_sl_tp_label,
    load_learning_state,
    resolve_sl_tp_from_backtest,
    symbol_passes_learning,
)
from app.engine.backtest_optimizer import BacktestAccumulator
from app.models import AppConfig, CoinCandidate, InvestmentRecommendation


def _format_news_detail(ns: NewsSymbolScore | None) -> str:
    if not ns:
        return ""
    parts: list[str] = []
    if ns.published_ts and ns.published_ts > 0:
        import time as _time

        parts.append(
            _time.strftime("%m/%d %H:%M", _time.localtime(ns.published_ts))
        )
    if ns.source:
        parts.append(ns.source)
    if ns.llm_reason:
        parts.append(f"AI: {ns.llm_reason}")
    if ns.headline:
        parts.append(ns.headline)
    elif ns.tag and not ns.llm_reason:
        parts.append(ns.tag)
    if ns.tag and ns.llm_reason and ns.tag not in parts:
        parts.append(ns.tag)
    return " · ".join(parts)


def _volume_rank_bonus(volume_usdt: float) -> float:
    """거래대금 큰 종목 우선 — log 스케일 0~18점."""
    vol = max(float(volume_usdt or 0), 0.0)
    if vol < 400_000:
        return 0.0
    return min(18.0, math.log10(vol / 400_000.0 + 1.0) * 8.0)


def _long_auto_volume_ok(volume_usdt: float) -> tuple[bool, str]:
    """자동 롱 — 최소 유동성 (단타보다 완화)."""
    from app.config import settings

    min_vol = float(getattr(settings, "min_quote_volume_usdt", 400_000.0))
    long_floor = max(min_vol, 800_000.0)
    vol = max(float(volume_usdt or 0), 0.0)
    if vol < long_floor:
        return False, (
            f"24h 거래대금 {vol / 1_000_000:.1f}M USDT "
            f"(롱 자동 ≥{long_floor / 1_000_000:.1f}M)"
        )
    return True, ""


def _tier_to_mode(tier: str) -> str:
    t = (tier or "").lower()
    if t == "scalp":
        return "scalp"
    if t == "moonshot":
        return "moonshot"
    return "long"


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
    *,
    min_buy_krw: float | None = None,
) -> list[float]:
    """
    점수 비중으로 현금 배분. 합계 <= deployable cash, 각 건 min_buy 이상(또는 0).
    """
    floor = max(UPBIT_MIN_ORDER_KRW, float(min_buy_krw or UPBIT_MIN_ORDER_KRW))

    if not weights or cash_krw < floor:
        return [0.0] * len(weights)

    budget = round(deployable_cash_krw(cash_krw, fee_pct), -3)
    if budget < floor:
        return [0.0] * len(weights)

    n = len(weights)
    max_slots = min(n, int(budget // floor))
    if max_slots <= 0:
        return [0.0] * n

    order = sorted(range(n), key=lambda i: weights[i], reverse=True)[:max_slots]
    sel_w = [weights[i] for i in order]
    wsum = sum(sel_w)
    if wsum <= 0:
        return [0.0] * n

    amts: list[float] = []
    for w in sel_w:
        amts.append(max(floor, round(budget * w / wsum, -3)))

    def _trim() -> None:
        nonlocal amts, order, sel_w
        while sum(amts) > budget and len(amts) > 1:
            amts.pop()
            order = order[: len(amts)]
            sel_w = sel_w[: len(amts)]
            wsum = sum(sel_w)
            amts = [max(floor, round(budget * w / wsum, -3)) for w in sel_w]

        while sum(amts) > budget and amts:
            over = sum(amts) - budget
            i = max(range(len(amts)), key=lambda j: amts[j])
            cut = min(over, amts[i] - floor)
            if cut < 1000:
                if len(amts) > 1:
                    amts.pop(i)
                    order.pop(i)
                    sel_w.pop(i)
                    wsum = sum(sel_w) or 1
                    amts = [max(floor, round(budget * w / wsum, -3)) for w in sel_w]
                else:
                    amts[i] = max(floor, budget)
                    break
            else:
                amts[i] = round(amts[i] - cut, -3)

    _trim()

    out = [0.0] * n
    for idx, a in zip(order, amts):
        if a >= floor:
            out[idx] = a

    while sum(out) > budget:
        active = [i for i in range(n) if out[i] >= floor]
        if not active:
            break
        i = max(active, key=lambda j: out[j])
        over = sum(out) - budget
        if out[i] - max(floor, over) >= floor:
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
    *,
    min_buy_krw: float | None = None,
) -> dict[str, float]:
    """승인 매수 합계가 현금을 넘지 않도록 비례 축소."""
    if not amounts:
        return amounts
    floor = max(UPBIT_MIN_ORDER_KRW, float(min_buy_krw or UPBIT_MIN_ORDER_KRW))
    budget = deployable_cash_krw(cash_krw, fee_pct)
    total = sum(amounts.values())
    if total <= budget:
        out = {k: max(floor, round(v, -3)) for k, v in amounts.items() if v >= floor}
    else:
        keys = list(amounts.keys())
        weights = [amounts[k] for k in keys]
        scaled = allocate_amounts_by_weights(
            weights, cash_krw, fee_pct, min_buy_krw=floor
        )
        out = {k: scaled[i] for i, k in enumerate(keys) if scaled[i] >= floor}

    # 매수 원금 + 편도 수수료 합이 현금을 넘지 않도록 최종 검증
    principal_sum = sum(out.values())
    need = cash_required_for_buy(principal_sum, fee_pct)
    if need > cash_krw and principal_sum > 0:
        scale = deployable_cash_krw(cash_krw, fee_pct) / principal_sum
        out = {
            k: max(floor, round(v * scale, -3))
            for k, v in out.items()
            if v * scale >= floor
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
    news_scores: dict[str, NewsSymbolScore] | None = None,
    live_meta: dict | None = None,
) -> list[InvestmentRecommendation]:
    """진입 가능 후보에 보유 현금 범위 내에서 점수 비중 배분."""
    fee_pct = float(getattr(config, "trading_fee_pct", 0.05))
    min_buy = effective_min_buy_krw(config)
    budget = deployable_cash_krw(cash_krw, fee_pct)
    if budget < min_buy:
        return []

    pool: list[CoinCandidate] = []
    entry_floor = config.min_entry_score * 0.85
    news_map = news_scores or {}
    for c in candidates:
        if c.symbol in held_symbols:
            continue
        if c.score < config.min_buy_score:
            continue
        ns = news_map.get(c.symbol.upper())
        news_pts = effective_news_score_for_moonshot(
            ns, c.symbol, live_meta, config
        )
        is_moon, _ = classify_moonshot(
            change_24h=c.change_24h,
            volume_usdt=float(getattr(c, "volume_usdt", 0) or 0),
            entry_score=c.entry_score,
            entry_ok=c.entry_ok,
            news_score=news_pts,
            config=config,
        )
        if is_moon:
            pool.append(c)
            continue
        if ns and effective_is_news_surge(ns, c.symbol, live_meta, config):
            pool.append(c)
            continue
        if c.entry_ok or getattr(c, "entry_scalp_ok", False):
            pool.append(c)
            continue
        if c.entry_score >= entry_floor:
            pool.append(c)

    def _rank(c: CoinCandidate) -> float:
        base = c.entry_score + c.score + _volume_rank_bonus(
            float(getattr(c, "volume_usdt", 0) or 0)
        )
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
    amounts = allocate_amounts_by_weights(
        weights, cash_krw, fee_pct, min_buy_krw=min_buy
    )
    total_allocated = sum(amounts)

    recs: list[InvestmentRecommendation] = []
    for c, amount, w in zip(pool, amounts, weights):
        if amount < min_buy:
            continue
        weight_pct = (
            round(amount / total_allocated * 100, 1) if total_allocated > 0 else 0.0
        )
        price_usdt = 0.0
        qty_est = 0.0
        ns = news_map.get(c.symbol.upper())
        news_flag = bool(
            ns and effective_is_news_surge(ns, c.symbol, live_meta, config)
        )
        news_pts = effective_news_score_for_moonshot(
            ns, c.symbol, live_meta, config
        )
        is_moon, moon_tag = classify_moonshot(
            change_24h=c.change_24h,
            volume_usdt=float(getattr(c, "volume_usdt", 0) or 0),
            entry_score=c.entry_score,
            entry_ok=c.entry_ok,
            news_score=news_pts,
            config=config,
        )
        if is_moon:
            tier = "moonshot"
        elif news_flag:
            tier = "moonshot"
            if not moon_tag:
                moon_tag = ns.tag if ns else "뉴스급등"
        elif c.entry_ok:
            tier = "auto"
        elif getattr(c, "entry_scalp_ok", False):
            tier = "scalp"
        else:
            tier = "watch"
        mode = _tier_to_mode(tier)
        strength_sl, strength_tp = strength_default_sl_tp(config)
        sl_use, tp_use, sl_src = resolve_sl_tp_from_backtest(
            acc,
            learning,
            c.symbol,
            mode=mode,
            default_sl=strength_sl,
            default_tp=strength_tp,
            config=config,
            change_24h=c.change_24h if mode == "moonshot" else 0.0,
            news_score=news_pts if mode == "moonshot" else 0.0,
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
                )
                + (f" · {moon_tag}" if (is_moon or news_flag) and moon_tag else "")
                + (f" · {ns.tag}" if ns and ns.tag and not moon_tag else ""),
                bt_line=_bt_line_for_symbol(acc, c.symbol, tier=tier),
                change_24h=c.change_24h,
                volume_usdt=float(getattr(c, "volume_usdt", 0) or 0),
                trend=c.trend,
                news_score=news_pts,
                news_surge=news_flag or (is_moon and news_pts >= float(
                    getattr(config, "news_boost_min_score", 25.0) or 25.0
                )),
                news_detail=_format_news_detail(ns),
                news_url=(ns.url if ns else "") or "",
                selected=True,
            )
        )
    return recs


def sync_surge_candidates(
    recs: list[InvestmentRecommendation],
    *,
    disabled: set[str] | None = None,
) -> tuple[int, list[str]]:
    """moonshot tier 제안 — status·뉴스 탭 자동매수 표시용."""
    disabled = disabled or set()
    symbols: list[str] = []
    seen: set[str] = set()
    for r in recs:
        if (r.entry_tier or "").lower() != "moonshot":
            continue
        sym = r.symbol.upper()
        if sym in disabled or sym in seen:
            continue
        seen.add(sym)
        symbols.append(sym)
    return len(symbols), symbols


def filter_recommendations_for_auto(
    recs: list[InvestmentRecommendation],
    *,
    auto_long: bool,
    auto_scalp: bool,
    acc: BacktestAccumulator | None,
    max_picks: int,
    flash_block_until: dict[str, float] | None = None,
    paper_relax_bt: bool = False,
    account_mode: str = "paper",
    disabled_surge: set[str] | None = None,
) -> list[InvestmentRecommendation]:
    """롱·단타·혼합 — 학습 임계값 통과한 제안만."""
    if not recs or max_picks <= 0:
        return []
    if not auto_long and not auto_scalp:
        return []

    learning = load_learning_state()
    acc = acc or BacktestAccumulator()
    from app.engine.flash_crash_guard import is_symbol_flash_blocked

    blocked_surge = disabled_surge or set()
    long_pool: list[InvestmentRecommendation] = []
    scalp_pool: list[InvestmentRecommendation] = []
    moon_pool: list[InvestmentRecommendation] = []
    for r in recs:
        if r.symbol.upper() in blocked_surge and (r.entry_tier or "").lower() == "moonshot":
            continue
        if flash_block_until and is_symbol_flash_blocked(flash_block_until, r.symbol):
            continue
        tier = (r.entry_tier or "").lower()
        if auto_long and tier == "moonshot":
            ok_vol, why_vol = _long_auto_volume_ok(
                float(getattr(r, "volume_usdt", 0) or 0)
            )
            if not ok_vol:
                continue
            ok, _ = symbol_passes_learning(
                acc,
                learning,
                r.symbol,
                mode="moonshot",
                paper_relax=paper_relax_bt,
                account_mode=account_mode,
            )
            if ok:
                moon_pool.append(r)
        elif auto_long and tier == "auto":
            ok_vol, why_vol = _long_auto_volume_ok(
                float(getattr(r, "volume_usdt", 0) or 0)
            )
            if not ok_vol:
                continue
            ok, _ = symbol_passes_learning(
                acc,
                learning,
                r.symbol,
                mode="long",
                paper_relax=paper_relax_bt,
                account_mode=account_mode,
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
                acc,
                learning,
                r.symbol,
                mode="scalp",
                paper_relax=paper_relax_bt,
                account_mode=account_mode,
            )
            if ok:
                scalp_pool.append(r)

    def _auto_rank(r: InvestmentRecommendation) -> float:
        return (
            r.entry_score
            + r.market_score
            + _volume_rank_bonus(float(getattr(r, "volume_usdt", 0) or 0))
        )

    long_pool.sort(key=_auto_rank, reverse=True)
    scalp_pool.sort(key=_auto_rank, reverse=True)
    moon_pool.sort(key=_auto_rank, reverse=True)

    picks: list[InvestmentRecommendation] = []
    if auto_long and auto_scalp:
        li, si, mi = 0, 0, 0
        pools = (moon_pool, long_pool, scalp_pool)
        idx = [0, 0, 0]
        while len(picks) < max_picks and any(i < len(p) for i, p in zip(idx, pools)):
            for pi, pool in enumerate(pools):
                if idx[pi] < len(pool) and len(picks) < max_picks:
                    picks.append(pool[idx[pi]])
                    idx[pi] += 1
            if all(idx[pi] >= len(pools[pi]) for pi in range(3)):
                break
    elif auto_long:
        merged: list[InvestmentRecommendation] = []
        seen: set[str] = set()
        for pool in (moon_pool, long_pool):
            for r in pool:
                sym = r.symbol.upper()
                if sym in seen:
                    continue
                seen.add(sym)
                merged.append(r)
        merged.sort(key=_auto_rank, reverse=True)
        picks = merged[:max_picks]
    else:
        picks = scalp_pool[:max_picks]
    return picks

"""실거래 주문 실행 + 동기화 (모의투자와 동일 메타·익절/손절 규칙)."""

import time
from typing import Optional

from app.engine.live_sync import export_live_meta, sync_live_portfolio
from app.engine.portfolio import PortfolioManager
from app.engine.portfolio_store import store
from app.market.upbit_data import market
from app.market.coin_registry import coin_meta
from app.market.upbit_client import symbol_to_upbit, upbit_client
from app.market.upbit_sell import (
    MIN_MARKET_ASK_KRW,
    clear_pending_exit,
    format_upbit_price,
    get_pending_exit,
    min_bid_for_market_sell,
    order_executed_qty,
    set_pending_exit,
    smart_sell,
)
from app.models import AppConfig, Position, TradeEvent
from app.storage.credentials import get_active_keys
from app.config import settings
from app.storage.persistence import save_live_meta

MIN_BUY_KRW = settings.min_buy_krw


def _persist_live(portfolio: PortfolioManager) -> None:
    prev = store._live_meta
    store._live_meta = export_live_meta(portfolio, preserve=prev)
    store._live_meta["realized_pnl_krw"] = portfolio.realized_pnl_krw
    save_live_meta(store._live_meta)


async def live_market_buy(
    config: AppConfig,
    symbol: str,
    amount_krw: float,
    reason: str,
    as_auto: bool = True,
    *,
    score: float = 0,
    entry_score: float = 0,
    entry_reason: str = "",
    entry_outlook: str = "",
) -> tuple[bool, str]:
    portfolio = store.live
    sym = symbol.upper()
    exchange = (config.exchange or "upbit").lower()
    if exchange != "upbit":
        return False, "AIDI는 업비트(KRW) 실거래만 지원합니다."

    if amount_krw < MIN_BUY_KRW:
        return False, f"최소 주문 금액은 {int(MIN_BUY_KRW):,}원입니다"

    before = PortfolioManager.position_snap(portfolio.positions.get(sym))

    quote_usdt = 0.0
    executed_qty = 0.0
    fills_price = 0.0
    try:
        from app.market.upbit_markets import get_upbit_krw_markets, resolve_upbit_market

        ak, sk = get_active_keys(config)
        upbit_client.configure(ak, sk)
        markets = await get_upbit_krw_markets()
        upbit_market = resolve_upbit_market(sym, markets)
        if not upbit_market:
            return False, f"업비트 미상장 종목 ({sym})"
        order = await upbit_client.market_buy_krw(upbit_market, amount_krw)
        executed_qty = float(order.get("executed_volume", 0))
        portfolio.usdt_krw = portfolio.usdt_krw or await market.usdt_krw_rate()
        fills_price = (amount_krw / max(executed_qty, 1e-12)) / portfolio.usdt_krw
        quote_usdt = amount_krw / portfolio.usdt_krw
    except Exception as e:
        return False, str(e)

    meta = store._live_meta
    await sync_live_portfolio(portfolio, config, meta)

    pos = portfolio.positions.get(sym)
    if pos:
        delta = max(0.0, pos.quantity - before["total"])
        if delta <= 0 and executed_qty > 0:
            delta = executed_qty
        portfolio.apply_live_buy_after_sync(
            pos,
            before,
            delta,
            fills_price,
            amount_krw,
            as_auto,
            config,
            reason=reason,
            entry_reason=entry_reason or reason,
            entry_score=entry_score,
            score=score,
            entry_outlook=entry_outlook,
        )

    m = coin_meta(sym)
    portfolio.trades.append(
        TradeEvent(
            ts=time.time(),
            symbol=sym,
            base=m["base"],
            display=m["display"],
            side="BUY",
            price=fills_price,
            quantity=executed_qty,
            amount_krw=round(amount_krw, 0),
            amount_usdt=round(quote_usdt, 4),
            reason=reason,
            is_auto=as_auto,
        )
    )

    _persist_live(portfolio)
    label = "업비트"
    mode = "AI 자동" if as_auto else "수동"
    return True, f"[{label}] 실거래 {mode} 매수 · {executed_qty:.6f}"


async def live_market_sell(
    config: AppConfig,
    symbol: str,
    percent: float,
    reason: str,
    auto_only: bool = False,
) -> tuple[bool, str]:
    portfolio = store.live
    sym = symbol.upper()
    pos = portfolio.positions.get(sym)
    if not pos:
        return False, "보유하지 않음"

    before = PortfolioManager.position_snap(pos)

    if auto_only:
        sell_qty = pos.auto_quantity * (percent / 100)
    else:
        sell_qty = pos.quantity * (percent / 100)

    if sell_qty <= 0:
        return False, "매도 수량 없음"

    exchange = (config.exchange or "upbit").lower()
    if exchange != "upbit":
        return False, "AIDI는 업비트(KRW) 실거래만 지원합니다."

    quote_krw = 0.0
    quote = 0.0
    executed_qty = 0.0
    price = pos.current_price or pos.avg_price
    try:
        from app.market.upbit_markets import get_upbit_krw_markets, resolve_upbit_market

        ak, sk = get_active_keys(config)
        upbit_client.configure(ak, sk)
        markets = await get_upbit_krw_markets()
        upbit_market = resolve_upbit_market(sym, markets)
        if not upbit_market:
            return False, f"업비트 미상장 종목 ({sym}) — 매도 스킵"
        bid_hint = 0.0
        if pos.current_price_krw > 0:
            bid_hint = pos.current_price_krw
        elif pos.current_price > 0 and portfolio.usdt_krw > 0:
            bid_hint = pos.current_price * portfolio.usdt_krw
        outcome = await smart_sell(
            upbit_client, upbit_market, sell_qty, bid_hint_krw=bid_hint
        )
        order = outcome.order
        sell_mode = outcome.mode
        executed_qty = order_executed_qty(order)
        if outcome.pending and executed_qty <= sell_qty * 1e-6:
            meta = store._live_meta
            need_bid = outcome.min_bid_for_market or min_bid_for_market_sell(
                sell_qty
            )
            set_pending_exit(
                meta,
                sym,
                reason=reason,
                min_bid_krw=need_bid,
                limit_price_krw=outcome.limit_price_krw,
            )
            save_live_meta(meta)
            need_tick = format_upbit_price(need_bid)
            lim = format_upbit_price(outcome.limit_price_krw)
            return (
                True,
                f"소액 포지션 — {lim}원 지정가 접수·감시 중 "
                f"(매수호가 {need_tick}원↑ 시 시장가 자동 재시도). "
                "업비트 앱 미체결에서도 확인 가능.",
            )
        if executed_qty <= sell_qty * 1e-6:
            return False, f"매도 체결 없음 ({sell_mode})"
        clear_pending_exit(store._live_meta, sym)
        quote_krw = executed_qty * pos.current_price * portfolio.usdt_krw
        if order.get("trades"):
            quote_krw = sum(float(t.get("funds", 0)) for t in order["trades"])
        price = quote_krw / max(executed_qty, 1e-12) / max(portfolio.usdt_krw, 1)
        quote = quote_krw / max(portfolio.usdt_krw, 1)
    except Exception as e:
        return False, str(e)

    meta = store._live_meta
    await sync_live_portfolio(portfolio, config, meta)

    pos_after: Optional[Position] = portfolio.positions.get(sym)
    pnl_delta = portfolio.apply_live_sell_after_sync(
        pos_after, before, executed_qty, price, auto_only
    )
    portfolio.realized_pnl_krw += pnl_delta

    m = coin_meta(sym)
    portfolio.trades.append(
        TradeEvent(
            ts=time.time(),
            symbol=sym,
            base=m["base"],
            display=m["display"],
            side="SELL",
            price=price,
            quantity=executed_qty,
            amount_krw=round(quote_krw, 0),
            amount_usdt=round(quote, 4),
            reason=reason,
            is_auto=auto_only,
        )
    )

    _persist_live(portfolio)
    label = "업비트"
    kind = "AI" if auto_only else "수동"
    tail = f" · {sell_mode}" if sell_mode != "시장가" else ""
    return True, f"[{label}] 실거래 {kind} 매도 · {executed_qty:.6f}{tail}"


async def retry_pending_exit_sells(config: AppConfig) -> None:
    """소액 pending_exit — 매수호가×수량이 5천원 이상이면 시장가 재시도."""
    meta = store._live_meta
    portfolio = store.live
    pending_syms = []
    for sym, pm in (meta.get("positions_meta") or {}).items():
        if isinstance(pm, dict) and pm.get("pending_exit"):
            pending_syms.append(sym.upper())
    if not pending_syms:
        return

    ak, sk = get_active_keys(config)
    if not ak or not sk:
        return

    from app.market.upbit_markets import get_upbit_krw_markets, resolve_upbit_market
    from app.market.upbit_sell import fetch_orderbook_top

    upbit_client.configure(ak, sk)
    markets = await get_upbit_krw_markets()

    for sym in pending_syms:
        pos = portfolio.positions.get(sym)
        pe = get_pending_exit(meta, sym)
        if not pe or not pos or pos.quantity <= 1e-12:
            clear_pending_exit(meta, sym)
            continue
        upbit_market = resolve_upbit_market(sym, markets)
        if not upbit_market:
            continue
        qty = pos.exchange_quantity or pos.quantity
        bid, _ = await fetch_orderbook_top(upbit_client, upbit_market)
        if bid <= 0 or qty * bid < MIN_MARKET_ASK_KRW - 0.5:
            continue
        qty_before = pos.quantity
        reason = str(pe.get("reason") or "대기 매도")
        ok, _msg = await live_market_sell(
            config, sym, 100.0, reason, auto_only=False
        )
        if not ok:
            continue
        await sync_live_portfolio(portfolio, config, meta)
        pos_after = portfolio.positions.get(sym)
        if not pos_after or pos_after.quantity < qty_before * 0.5:
            clear_pending_exit(meta, sym)
            save_live_meta(meta)

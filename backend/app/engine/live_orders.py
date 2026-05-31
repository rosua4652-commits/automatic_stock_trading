"""실거래 주문 실행 + 동기화 (모의투자와 동일 메타·익절/손절 규칙)."""

import time
from typing import Optional

from app.engine.live_sync import export_live_meta, sync_live_portfolio
from app.engine.portfolio import PortfolioManager
from app.engine.portfolio_store import store
from app.engine.trade_history import (
    classify_exit_kind,
    merge_trade_events,
    normalize_trade_reason,
    remember_order_reason,
    remember_order_uuid,
)
from app.market.coin_registry import coin_meta
from app.market.upbit_data import market
from app.market.upbit_client import upbit_client
from app.market.upbit_order_fill import (
    repair_trade_dict,
    resolve_upbit_fill,
)
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
    rate = max(portfolio.usdt_krw, 1.0)
    store._live_meta["trades"] = [
        repair_trade_dict(t.model_dump(), usdt_krw=rate)
        for t in portfolio.trades[-100:]
    ]
    save_live_meta(store._live_meta)


async def _sync_live_refresh(portfolio: PortfolioManager, config: AppConfig) -> None:
    prev = store._live_meta
    await sync_live_portfolio(portfolio, config, prev)


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
    async with store._lock:
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
        price_krw = 0.0
        fill_krw = 0.0
        order_uuid = ""
        try:
            from app.market.upbit_markets import get_upbit_krw_markets, resolve_upbit_market

            ak, sk = get_active_keys(config)
            upbit_client.configure(ak, sk)
            markets = await get_upbit_krw_markets()
            upbit_market = resolve_upbit_market(sym, markets)
            if not upbit_market:
                return False, f"업비트 미상장 종목 ({sym})"
            order = await upbit_client.market_buy_krw(upbit_market, amount_krw)
            portfolio.usdt_krw = portfolio.usdt_krw or await market.usdt_krw_rate()
            price_hint = 0.0
            tick = await upbit_client.tickers([upbit_market])
            if tick.get(upbit_market):
                price_hint = float(tick[upbit_market].get("trade_price") or 0)
            executed_qty, fill_krw, price_krw = await resolve_upbit_fill(
                upbit_client,
                order,
                amount_krw_hint=amount_krw,
                price_krw_hint=price_hint,
                fallback_qty=amount_krw / max(price_hint, 1.0) if price_hint > 0 else 0.0,
            )
            fills_price = (
                price_krw / max(portfolio.usdt_krw, 1.0) if price_krw > 0 else 0.0
            )
            if fills_price <= 0 and executed_qty > 0:
                fills_price = (fill_krw or amount_krw) / max(
                    executed_qty * max(portfolio.usdt_krw, 1.0), 1e-12
                )
            quote_usdt = (fill_krw or amount_krw) / max(portfolio.usdt_krw, 1.0)
            order_uuid = str(order.get("uuid") or "")
            if order_uuid:
                remember_order_uuid(store._live_meta, order_uuid)
                remember_order_reason(
                    store._live_meta,
                    order_uuid,
                    reason=reason,
                    is_auto=as_auto,
                    side="BUY",
                )
        except Exception as e:
            return False, str(e)

        store._live_meta["trades_force_sync"] = True
        await _sync_live_refresh(portfolio, config)

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

        if order_uuid and executed_qty > 0:
            m = coin_meta(sym)
            reason_label = normalize_trade_reason(
                "BUY", reason, is_auto=as_auto, has_aidi_hint=True
            )
            portfolio.trades = merge_trade_events(
                portfolio.trades,
                [
                    TradeEvent(
                        ts=time.time(),
                        symbol=sym,
                        base=m["base"],
                        display=m["display"],
                        side="BUY",
                        price=fills_price,
                        price_krw=round(
                            price_krw
                            if price_krw > 0
                            else (fill_krw or amount_krw) / max(executed_qty, 1e-12),
                            4,
                        ),
                        quantity=executed_qty,
                        amount_krw=round(fill_krw or amount_krw, 0),
                        amount_usdt=round(quote_usdt, 4),
                        reason=reason_label,
                        is_auto=as_auto,
                        order_uuid=order_uuid,
                    )
                ],
                usdt_krw=max(portfolio.usdt_krw, 1.0),
            )

        _persist_live(portfolio)
        label = "업비트"
        mode = "AI 자동" if as_auto else "수동"
        qty_txt = f"{executed_qty:.6f}".rstrip("0").rstrip(".")
        return True, f"[{label}] 실거래 {mode} 매수 · {qty_txt}개 · {int(fill_krw or amount_krw):,}원"


async def live_market_sell(
    config: AppConfig,
    symbol: str,
    percent: float,
    reason: str,
    auto_only: bool = False,
    *,
    reason_is_auto: bool | None = None,
) -> tuple[bool, str]:
    record_auto = reason_is_auto if reason_is_auto is not None else auto_only

    async with store._lock:
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
        price_krw = 0.0
        sell_mode = "시장가"
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
            if bid_hint <= 0:
                tick = await upbit_client.tickers([upbit_market])
                if tick.get(upbit_market):
                    bid_hint = float(tick[upbit_market].get("trade_price") or 0)
            outcome = await smart_sell(
                upbit_client, upbit_market, sell_qty, bid_hint_krw=bid_hint
            )
            order = outcome.order
            sell_mode = outcome.mode
            order_uuid = str(order.get("uuid") or "")
            raw_qty = order_executed_qty(order)
            if outcome.pending and raw_qty <= sell_qty * 1e-6:
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
                    order_uuid=order_uuid,
                )
                if order_uuid:
                    remember_order_uuid(meta, order_uuid)
                    remember_order_reason(
                        meta,
                        order_uuid,
                        reason=reason,
                        is_auto=True,
                        side="SELL",
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
            if raw_qty <= sell_qty * 1e-6:
                filled_now, _, _ = await resolve_upbit_fill(
                    upbit_client,
                    order,
                    price_krw_hint=bid_hint,
                    fallback_qty=sell_qty,
                )
                if filled_now <= sell_qty * 1e-6:
                    return False, f"매도 체결 없음 ({sell_mode})"
                raw_qty = filled_now
            clear_pending_exit(store._live_meta, sym)
            executed_qty, quote_krw, price_krw = await resolve_upbit_fill(
                upbit_client,
                order,
                price_krw_hint=bid_hint,
                fallback_qty=max(raw_qty, sell_qty),
            )
            if executed_qty <= 1e-12:
                return False, f"매도 체결 정보 없음 ({sell_mode})"
            if order_uuid:
                remember_order_uuid(store._live_meta, order_uuid)
                remember_order_reason(
                    store._live_meta,
                    order_uuid,
                    reason=reason,
                    is_auto=record_auto,
                    side="SELL",
                )
            price = price_krw / max(portfolio.usdt_krw, 1.0) if price_krw > 0 else 0.0
            if price <= 0 and pos.current_price > 0:
                price = pos.current_price
            quote = quote_krw / max(portfolio.usdt_krw, 1.0)
        except Exception as e:
            return False, str(e)

        store._live_meta["trades_force_sync"] = True
        await _sync_live_refresh(portfolio, config)

        pos_after: Optional[Position] = portfolio.positions.get(sym)
        pnl_delta = portfolio.apply_live_sell_after_sync(
            pos_after, before, executed_qty, price, auto_only
        )
        portfolio.realized_pnl_krw += pnl_delta

        if order_uuid and executed_qty > 0:
            m = coin_meta(sym)
            reason_label = normalize_trade_reason(
                "SELL",
                reason,
                is_auto=record_auto,
                has_aidi_hint=True,
                exit_kind=classify_exit_kind(reason, "SELL"),
            )
            portfolio.trades = merge_trade_events(
                portfolio.trades,
                [
                    TradeEvent(
                        ts=time.time(),
                        symbol=sym,
                        base=m["base"],
                        display=m["display"],
                        side="SELL",
                        price=price,
                        price_krw=round(price_krw, 4) if price_krw > 0 else 0.0,
                        quantity=executed_qty,
                        amount_krw=round(quote_krw, 0),
                        amount_usdt=round(quote, 4),
                        reason=reason_label,
                        is_auto=auto_only,
                        order_uuid=order_uuid,
                    )
                ],
                usdt_krw=max(portfolio.usdt_krw, 1.0),
            )

        _persist_live(portfolio)
        label = "업비트"
        kind = "AI" if auto_only else "수동"
        tail = f" · {sell_mode}" if sell_mode != "시장가" else ""
        qty_txt = f"{executed_qty:.6f}".rstrip("0").rstrip(".")
        return True, (
            f"[{label}] 실거래 {kind} 매도 · {qty_txt}개 · "
            f"{int(quote_krw):,}원{tail}"
        )


async def retry_pending_exit_sells(config: AppConfig) -> None:
    """소액 pending_exit — 매수호가×수량이 5천원 이상이면 시장가 재시도."""
    async with store._lock:
        meta = store._live_meta
        portfolio = store.live
        pending_syms = [
            sym.upper()
            for sym, pm in (meta.get("positions_meta") or {}).items()
            if isinstance(pm, dict) and pm.get("pending_exit")
        ]
        if not pending_syms:
            return

        ak, sk = get_active_keys(config)
        if not ak or not sk:
            return

        from app.market.upbit_markets import get_upbit_krw_markets, resolve_upbit_market
        from app.market.upbit_sell import fetch_orderbook_top

        upbit_client.configure(ak, sk)
        markets = await get_upbit_krw_markets()
        retry_jobs: list[tuple[str, str, float]] = []

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
            retry_jobs.append(
                (sym, str(pe.get("reason") or "대기 매도"), pos.quantity)
            )
        if retry_jobs:
            save_live_meta(meta)

    for sym, reason, qty_before in retry_jobs:
        ok, _msg = await live_market_sell(
            config,
            sym,
            100.0,
            reason,
            auto_only=False,
            reason_is_auto=True,
        )
        if not ok:
            continue
        async with store._lock:
            meta = store._live_meta
            portfolio = store.live
            pos_after = portfolio.positions.get(sym)
            if not pos_after or pos_after.quantity < qty_before * 0.5:
                clear_pending_exit(meta, sym)
                save_live_meta(meta)

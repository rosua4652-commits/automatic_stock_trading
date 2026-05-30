"""실거래 주문 실행 + 동기화 (모의투자와 동일 메타·익절/손절 규칙)."""

import time
from typing import Optional

from app.engine.live_sync import export_live_meta, sync_live_portfolio
from app.engine.portfolio import PortfolioManager
from app.engine.portfolio_store import store
from app.market.binance_live import binance_live
from app.market.coin_registry import coin_meta
from app.market.upbit_client import symbol_to_upbit, upbit_client
from app.models import AppConfig, Position, TradeEvent
from app.storage.credentials import get_active_keys
from app.config import settings
from app.storage.persistence import save_live_meta

MIN_BUY_KRW = settings.min_buy_krw


def _persist_live(portfolio: PortfolioManager) -> None:
    store._live_meta = export_live_meta(portfolio)
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

    if amount_krw < MIN_BUY_KRW:
        return False, f"최소 주문 금액은 {int(MIN_BUY_KRW):,}원입니다"

    before = PortfolioManager.position_snap(portfolio.positions.get(sym))

    quote_usdt = 0.0
    executed_qty = 0.0
    fills_price = 0.0
    try:
        if exchange == "upbit":
            from app.market.upbit_markets import get_upbit_krw_markets, resolve_upbit_market

            ak, sk = get_active_keys(config)
            upbit_client.configure(ak, sk)
            markets = await get_upbit_krw_markets()
            market = resolve_upbit_market(sym, markets)
            if not market:
                return (
                    False,
                    f"업비트 미상장 종목 ({sym}). 바이낸스 전용·밈코인은 업비트 실거래 불가.",
                )
            order = await upbit_client.market_buy_krw(market, amount_krw)
            executed_qty = float(order.get("executed_volume", 0))
            portfolio.usdt_krw = portfolio.usdt_krw or 1350
            fills_price = (amount_krw / max(executed_qty, 1e-12)) / portfolio.usdt_krw
            quote_usdt = amount_krw / portfolio.usdt_krw
        else:
            portfolio.usdt_krw = portfolio.usdt_krw or 1350
            quote_usdt = portfolio.krw_to_usdt(amount_krw)
            if quote_usdt < 5:
                return False, "최소 주문 금액 미달"
            ak, sk = get_active_keys(config)
            binance_live.configure(ak, sk, testnet=getattr(config, "use_testnet", False))
            order = await binance_live.market_buy_quote(sym, quote_usdt)
            executed_qty = float(order.get("executedQty", 0))
            fills_price = float(order.get("cummulativeQuoteQty", quote_usdt)) / max(
                executed_qty, 1e-12
            )
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
    label = "업비트" if exchange == "upbit" else "Binance"
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

    quote_krw = 0.0
    quote = 0.0
    executed_qty = 0.0
    price = pos.current_price or pos.avg_price
    try:
        if exchange == "upbit":
            from app.market.upbit_markets import get_upbit_krw_markets, resolve_upbit_market

            ak, sk = get_active_keys(config)
            upbit_client.configure(ak, sk)
            markets = await get_upbit_krw_markets()
            market = resolve_upbit_market(sym, markets)
            if not market:
                return False, f"업비트 미상장 종목 ({sym}) — 매도 스킵"
            order = await upbit_client.market_sell(market, sell_qty)
            executed_qty = float(order.get("executed_volume", sell_qty))
            quote_krw = executed_qty * pos.current_price * portfolio.usdt_krw
            if order.get("trades"):
                quote_krw = sum(float(t.get("funds", 0)) for t in order["trades"])
            price = quote_krw / max(executed_qty, 1e-12) / max(portfolio.usdt_krw, 1)
            quote = quote_krw / max(portfolio.usdt_krw, 1)
        else:
            ak, sk = get_active_keys(config)
            binance_live.configure(ak, sk, testnet=getattr(config, "use_testnet", False))
            order = await binance_live.market_sell_qty(sym, sell_qty)
            executed_qty = float(order.get("executedQty", sell_qty))
            quote = float(order.get("cummulativeQuoteQty", 0))
            price = quote / max(executed_qty, 1e-12)
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
            amount_krw=round(
                quote_krw if exchange == "upbit" else quote * portfolio.usdt_krw, 0
            ),
            amount_usdt=round(quote, 4),
            reason=reason,
            is_auto=auto_only,
        )
    )

    _persist_live(portfolio)
    label = "업비트" if exchange == "upbit" else "Binance"
    kind = "AI" if auto_only else "수동"
    return True, f"[{label}] 실거래 {kind} 매도 · {executed_qty:.6f}"

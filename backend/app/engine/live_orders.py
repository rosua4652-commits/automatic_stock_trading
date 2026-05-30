"""실거래 주문 실행 + 동기화."""

from app.engine.live_sync import export_live_meta, sync_live_portfolio
from app.engine.portfolio_store import store
from app.market.binance_live import binance_live
from app.models import AppConfig, TradeEvent
from app.storage.persistence import save_live_meta
import time

from app.market.coin_registry import coin_meta


async def _qty_before(portfolio, symbol: str) -> tuple[float, float]:
    p = portfolio.positions.get(symbol)
    if not p:
        return 0.0, 0.0
    return p.quantity, p.auto_quantity


async def live_market_buy(
    config: AppConfig,
    symbol: str,
    amount_krw: float,
    reason: str,
    as_auto: bool = True,
) -> tuple[bool, str]:
    portfolio = store.live
    portfolio.usdt_krw = portfolio.usdt_krw or 1350
    quote_usdt = portfolio.krw_to_usdt(amount_krw)
    if quote_usdt < 5:
        return False, "최소 주문 금액 미달"

    binance_live.configure(
        config.binance_api_key,
        config.binance_api_secret,
        testnet=getattr(config, "use_testnet", False),
    )

    sym = symbol.upper()
    old_total, old_auto = await _qty_before(portfolio, sym)

    try:
        order = await binance_live.market_buy_quote(sym, quote_usdt)
    except Exception as e:
        return False, str(e)

    executed_qty = float(order.get("executedQty", 0))
    fills_price = float(order.get("cummulativeQuoteQty", quote_usdt)) / max(executed_qty, 1e-12)

    meta = store._live_meta
    await sync_live_portfolio(portfolio, config, meta)

    pos = portfolio.positions.get(sym)
    if pos and as_auto:
        delta = max(0, pos.quantity - old_total)
        pos.auto_quantity = min(pos.quantity, old_auto + delta)
        pos.manual_quantity = max(0, pos.quantity - pos.auto_quantity)
        if pos.auto_avg_price <= 0:
            pos.auto_avg_price = fills_price
        pos.auto_cost_basis_krw += amount_krw * (delta / pos.quantity if pos.quantity else 1)
        sl = config.stop_loss_pct / 100
        tp = config.take_profit_pct / 100
        pos.stop_loss = fills_price * (1 - sl)
        pos.take_profit = fills_price * (1 + tp)
        pos.trailing_high = fills_price
        pos.entry_reason = reason

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

    store._live_meta = export_live_meta(portfolio)
    save_live_meta(store._live_meta)
    return True, f"실거래 매수 체결 · {executed_qty:.6f}"


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

    if auto_only:
        sell_qty = pos.auto_quantity * (percent / 100)
    else:
        sell_qty = pos.quantity * (percent / 100)

    if sell_qty <= 0:
        return False, "매도 수량 없음"

    binance_live.configure(
        config.binance_api_key,
        config.binance_api_secret,
        testnet=getattr(config, "use_testnet", False),
    )

    try:
        order = await binance_live.market_sell_qty(sym, sell_qty)
    except Exception as e:
        return False, str(e)

    executed_qty = float(order.get("executedQty", sell_qty))
    quote = float(order.get("cummulativeQuoteQty", 0))
    price = quote / max(executed_qty, 1e-12)

    meta = store._live_meta
    await sync_live_portfolio(portfolio, config, meta)

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
            amount_krw=round(portfolio.usdt_to_krw(quote), 0),
            amount_usdt=round(quote, 4),
            reason=reason,
            is_auto=auto_only,
        )
    )

    store._live_meta = export_live_meta(portfolio)
    save_live_meta(store._live_meta)
    return True, f"실거래 매도 체결 · {executed_qty:.6f}"

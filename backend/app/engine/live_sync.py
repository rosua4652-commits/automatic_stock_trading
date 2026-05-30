"""실거래: 거래소 계정 → 포트폴리오 동기화 (시뮬 데이터와 무관)."""

import time
from typing import Any

from app.market.binance import binance
from app.market.binance_live import binance_live
from app.market.coin_registry import coin_meta
from app.market.upbit_client import symbol_to_upbit, upbit_client, upbit_to_symbol
from app.models import AppConfig, Position, TradeEvent
from app.storage.credentials import get_active_keys

STABLE = {"USDT", "USDC", "BUSD", "FDUSD", "DAI", "TUSD", "KRW"}


async def sync_live_portfolio(
    portfolio,
    config: AppConfig,
    live_meta: dict[str, Any],
) -> str:
    """
    거래소 잔고를 기준으로 live 포트폴리오 재구성.
    live_meta: AIDI 전용 메타 (auto/manual 분리, 익절선 등) — 잔고는 거래소가 진실.
    """
    ak, sk = get_active_keys(config)
    if not ak or not sk:
        raise RuntimeError("API 키를 설정하세요")

    exchange = (config.exchange or "upbit").lower()
    if exchange == "upbit":
        return await _sync_upbit(portfolio, config, live_meta, ak, sk)
    return await _sync_binance(portfolio, config, live_meta, ak, sk)


async def _sync_upbit(
    portfolio,
    config: AppConfig,
    live_meta: dict[str, Any],
    access_key: str,
    secret_key: str,
) -> str:
    upbit_client.configure(access_key, secret_key)
    accounts = await upbit_client.accounts()
    portfolio.usdt_krw = await binance.usdt_krw_rate()
    meta_map: dict = live_meta.get("positions_meta", {})

    krw_cash = 0.0
    holdings: dict[str, float] = {}

    for bal in accounts:
        cur = bal.get("currency", "")
        free = float(bal.get("balance", 0))
        locked = float(bal.get("locked", 0))
        total = free + locked
        if total <= 0:
            continue
        if cur == "KRW":
            krw_cash = total
            continue
        market = f"KRW-{cur}"
        holdings[market] = total

    tickers = await upbit_client.tickers(list(holdings.keys()))
    new_positions: dict[str, Position] = {}

    for market, total_qty in holdings.items():
        t = tickers.get(market)
        if not t:
            continue
        price_krw = float(t.get("trade_price", 0))
        if price_krw <= 0:
            continue
        price_usdt = price_krw / portfolio.usdt_krw
        symbol = upbit_to_symbol(market)
        base = market.replace("KRW-", "")
        pm = meta_map.get(symbol, {})

        auto_q = min(float(pm.get("auto_quantity", 0)), total_qty)
        manual_q = max(0.0, total_qty - auto_q)
        if pm.get("excluded_from_auto"):
            manual_q = total_qty
            auto_q = min(float(pm.get("auto_quantity", 0)), max(0, total_qty - manual_q))

        auto_cost = float(pm.get("auto_cost_basis_krw", 0))
        man_cost = float(pm.get("manual_cost_basis_krw", 0))
        if auto_q <= 0:
            auto_cost = 0
        if manual_q <= 0:
            man_cost = 0

        cm = coin_meta(symbol, base)
        sl = float(pm.get("stop_loss", 0))
        tp = float(pm.get("take_profit", 0))
        if auto_q > 0 and sl <= 0:
            sl = price_usdt * (1 - config.stop_loss_pct / 100)
            tp = price_usdt * (1 + config.take_profit_pct / 100)

        pos = Position(
            symbol=symbol,
            base=cm["base"],
            name_ko=cm["name_ko"],
            name_en=cm["name_en"],
            pair_label=cm["pair_label"],
            display=cm["display"],
            auto_quantity=auto_q,
            manual_quantity=manual_q,
            avg_price=price_usdt,
            auto_avg_price=float(pm.get("auto_avg_price", price_usdt)) if auto_q else 0,
            manual_avg_price=float(pm.get("manual_avg_price", price_usdt)) if manual_q else 0,
            current_price=price_usdt,
            stop_loss=sl,
            take_profit=tp,
            trailing_high=float(pm.get("trailing_high", price_usdt)),
            opened_at=float(pm.get("opened_at", time.time())),
            score=float(pm.get("score", 0)),
            cost_basis_krw=auto_cost + man_cost,
            auto_cost_basis_krw=auto_cost,
            manual_cost_basis_krw=man_cost,
            entry_reason=pm.get("entry_reason", "업비트 동기화"),
            entry_score=float(pm.get("entry_score", 0)),
            entry_outlook=pm.get("entry_outlook", ""),
            excluded_from_auto=bool(pm.get("excluded_from_auto", False)),
        )
        if total_qty > 1e-10:
            new_positions[symbol] = pos

    portfolio.positions = new_positions
    portfolio.cash_krw = krw_cash
    portfolio.realized_pnl_krw = float(live_meta.get("realized_pnl_krw", 0))

    local_trades = [TradeEvent(**t) for t in live_meta.get("trades", [])[-100:]]
    portfolio.trades = local_trades

    n = len(new_positions)
    coin_value = sum(
        p.quantity * p.current_price * portfolio.usdt_krw
        for p in new_positions.values()
    )
    total_krw = portfolio.cash_krw + coin_value
    return (
        f"[업비트 실거래] 연동 · 보유 {n}종 · "
        f"총자산 약 {total_krw:,.0f}원 (KRW {krw_cash:,.0f})"
    )


async def _sync_binance(
    portfolio,
    config: AppConfig,
    live_meta: dict[str, Any],
    access_key: str,
    secret_key: str,
) -> str:
    binance_live.configure(
        access_key,
        secret_key,
        testnet=getattr(config, "use_testnet", False),
    )

    account = await binance_live.account()
    tickers = await binance.tickers_24h()
    portfolio.usdt_krw = await binance.usdt_krw_rate()
    meta_map: dict = live_meta.get("positions_meta", {})

    usdt_free = 0.0
    new_positions: dict[str, Position] = {}

    for bal in account.get("balances", []):
        asset = bal.get("asset", "")
        free = float(bal.get("free", 0))
        locked = float(bal.get("locked", 0))
        total = free + locked
        if total <= 0:
            continue

        if asset in STABLE:
            if asset == "USDT":
                usdt_free = free
            continue

        symbol = f"{asset}USDT"
        t = tickers.get(symbol)
        if not t:
            continue

        price = float(t["lastPrice"])
        total_qty = total
        pm = meta_map.get(symbol, {})

        auto_q = min(float(pm.get("auto_quantity", 0)), total_qty)
        manual_q = max(0.0, total_qty - auto_q)
        if pm.get("excluded_from_auto"):
            manual_q = total_qty
            auto_q = min(float(pm.get("auto_quantity", 0)), max(0, total_qty - manual_q))

        auto_cost = float(pm.get("auto_cost_basis_krw", 0))
        man_cost = float(pm.get("manual_cost_basis_krw", 0))
        if auto_q <= 0:
            auto_cost = 0
        if manual_q <= 0:
            man_cost = 0

        cm = coin_meta(symbol, asset)
        sl = float(pm.get("stop_loss", 0))
        tp = float(pm.get("take_profit", 0))
        if auto_q > 0 and sl <= 0:
            sl = price * (1 - config.stop_loss_pct / 100)
            tp = price * (1 + config.take_profit_pct / 100)

        pos = Position(
            symbol=symbol,
            base=cm["base"],
            name_ko=cm["name_ko"],
            name_en=cm["name_en"],
            pair_label=cm["pair_label"],
            display=cm["display"],
            auto_quantity=auto_q,
            manual_quantity=manual_q,
            avg_price=price,
            auto_avg_price=float(pm.get("auto_avg_price", price)) if auto_q else 0,
            manual_avg_price=float(pm.get("manual_avg_price", price)) if manual_q else 0,
            current_price=price,
            stop_loss=sl,
            take_profit=tp,
            trailing_high=float(pm.get("trailing_high", price)),
            opened_at=float(pm.get("opened_at", time.time())),
            score=float(pm.get("score", 0)),
            cost_basis_krw=auto_cost + man_cost,
            auto_cost_basis_krw=auto_cost,
            manual_cost_basis_krw=man_cost,
            entry_reason=pm.get("entry_reason", "거래소 동기화"),
            entry_score=float(pm.get("entry_score", 0)),
            entry_outlook=pm.get("entry_outlook", ""),
            excluded_from_auto=bool(pm.get("excluded_from_auto", False)),
        )
        if total_qty > 1e-10:
            new_positions[symbol] = pos

    portfolio.positions = new_positions
    portfolio.cash_krw = portfolio.usdt_to_krw(usdt_free)
    portfolio.realized_pnl_krw = float(live_meta.get("realized_pnl_krw", 0))

    local_trades = [TradeEvent(**t) for t in live_meta.get("trades", [])[-100:]]
    portfolio.trades = local_trades

    n = len(new_positions)
    total_krw = portfolio.cash_krw + sum(
        portfolio.usdt_to_krw(p.quantity * p.current_price)
        for p in new_positions.values()
    )
    net = "테스트넷" if getattr(config, "use_testnet", False) else "실거래"
    return f"[Binance {net}] 연동 · 보유 {n}종 · 총자산 약 {total_krw:,.0f}원 (USDT {usdt_free:.2f})"


def export_live_meta(portfolio) -> dict[str, Any]:
    """포트폴리오 → AIDI 메타 저장 (잔고 제외)."""
    positions_meta = {}
    for sym, pos in portfolio.positions.items():
        positions_meta[sym] = {
            "auto_quantity": pos.auto_quantity,
            "manual_quantity": pos.manual_quantity,
            "auto_avg_price": pos.auto_avg_price,
            "manual_avg_price": pos.manual_avg_price,
            "auto_cost_basis_krw": pos.auto_cost_basis_krw,
            "manual_cost_basis_krw": pos.manual_cost_basis_krw,
            "stop_loss": pos.stop_loss,
            "take_profit": pos.take_profit,
            "trailing_high": pos.trailing_high,
            "opened_at": pos.opened_at,
            "score": pos.score,
            "entry_reason": pos.entry_reason,
            "entry_score": pos.entry_score,
            "entry_outlook": pos.entry_outlook,
            "excluded_from_auto": pos.excluded_from_auto,
        }
    return {
        "positions_meta": positions_meta,
        "trades": [t.model_dump() for t in portfolio.trades[-100:]],
        "realized_pnl_krw": portfolio.realized_pnl_krw,
    }

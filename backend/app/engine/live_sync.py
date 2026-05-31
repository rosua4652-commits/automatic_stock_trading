"""실거래: 거래소 계정 → 포트폴리오 동기화 (시뮬 데이터와 무관)."""

import time
from typing import Any

from app.market.upbit_data import market as upbit_feed
from app.market.binance_live import binance_live
from app.market.coin_registry import coin_meta
from app.market.upbit_client import symbol_to_upbit, upbit_client, upbit_to_symbol
from app.engine.trade_history import (
    backfill_recent_sells,
    merge_trade_dicts,
    merge_trade_events,
)
from app.market.upbit_order_fill import repair_trade_dict
from app.models import (
    AppConfig,
    Position,
    TradeEvent,
    UpbitAccountSnapshot,
    UpbitHoldingRow,
)
from app.storage.credentials import get_active_keys

STABLE = {"USDT", "USDC", "BUSD", "FDUSD", "DAI", "TUSD", "KRW"}


def _parse_avg_buy_krw(balance: dict) -> float:
    """업비트 계정 avg_buy_price (KRW/코인)."""
    try:
        v = float(balance.get("avg_buy_price") or 0)
    except (TypeError, ValueError):
        return 0.0
    return v if v > 0 else 0.0


def _resolve_position_costs(
    pm: dict,
    *,
    total_qty: float,
    auto_q: float,
    manual_q: float,
    avg_buy_krw: float,
    price_krw: float,
    usdt_krw: float,
) -> tuple[float, float, float, float]:
    """
    AIDI 메타에 원금이 없으면 업비트 평단(avg_buy_price)으로 추정.
    Returns: auto_cost, man_cost, auto_avg_usdt, manual_avg_usdt
    """
    auto_cost = float(pm.get("auto_cost_basis_krw", 0))
    man_cost = float(pm.get("manual_cost_basis_krw", 0))
    if auto_q <= 0:
        auto_cost = 0.0
    if manual_q <= 0:
        man_cost = 0.0

    total_cost = auto_cost + man_cost
    if avg_buy_krw > 0 and total_qty > 1e-12:
        total_cost = avg_buy_krw * total_qty
        if auto_q > 0 and manual_q > 0:
            ratio_a = (
                auto_cost / (auto_cost + man_cost)
                if (auto_cost + man_cost) > 0
                else auto_q / total_qty
            )
            auto_cost = total_cost * ratio_a
            man_cost = total_cost - auto_cost
        elif auto_q > 0:
            auto_cost = total_cost
            man_cost = 0.0
        else:
            man_cost = total_cost
            auto_cost = 0.0
    elif total_cost <= 0 and total_qty > 1e-12:
        if price_krw > 0:
            total_cost = price_krw * total_qty
        if total_cost > 0:
            if auto_q > 0 and manual_q > 0:
                auto_cost = total_cost * (auto_q / total_qty)
                man_cost = total_cost - auto_cost
            elif auto_q > 0:
                auto_cost = total_cost
            else:
                man_cost = total_cost

    avg_usdt = (avg_buy_krw / usdt_krw) if avg_buy_krw > 0 and usdt_krw > 0 else 0.0
    if avg_usdt <= 0 and price_krw > 0 and usdt_krw > 0:
        avg_usdt = price_krw / usdt_krw

    auto_avg = float(pm.get("auto_avg_price", 0)) if auto_q > 0 else 0.0
    manual_avg = float(pm.get("manual_avg_price", 0)) if manual_q > 0 else 0.0
    if avg_buy_krw > 0 and usdt_krw > 0:
        truth_avg = avg_buy_krw / usdt_krw
        if manual_q > 0:
            manual_avg = truth_avg
        if auto_q > 0:
            auto_avg = truth_avg
    else:
        if auto_q > 0 and auto_avg <= 0 and avg_usdt > 0:
            auto_avg = avg_usdt
        if manual_q > 0 and manual_avg <= 0 and avg_usdt > 0:
            manual_avg = avg_usdt

    return auto_cost, man_cost, auto_avg, manual_avg


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
    if exchange != "upbit":
        raise RuntimeError("AIDI는 업비트(KRW)만 지원합니다.")
    return await _sync_upbit(portfolio, config, live_meta, ak, sk)


async def _sync_upbit(
    portfolio,
    config: AppConfig,
    live_meta: dict[str, Any],
    access_key: str,
    secret_key: str,
) -> str:
    from app.market.upbit_markets import get_upbit_krw_markets

    upbit_client.configure(access_key, secret_key)
    allowed_markets = await get_upbit_krw_markets()
    accounts = await upbit_client.accounts()
    portfolio.usdt_krw = await upbit_feed.usdt_krw_rate()
    meta_map: dict = live_meta.get("positions_meta", {})

    prev_qty: dict[str, float] = {}
    for sym, pos in portfolio.positions.items():
        prev_qty[sym.upper()] = float(
            getattr(pos, "exchange_quantity", pos.quantity) or pos.quantity
        )
    for sym, qty in (live_meta.get("last_holdings_qty") or {}).items():
        sym_u = str(sym).upper()
        if sym_u not in prev_qty and float(qty or 0) > 1e-12:
            prev_qty[sym_u] = float(qty)
    pending_reasons: dict[str, str] = {}
    for sym, pm in meta_map.items():
        if not isinstance(pm, dict):
            continue
        pe = pm.get("pending_exit")
        if isinstance(pe, dict):
            pending_reasons[str(sym).upper()] = str(pe.get("reason") or "대기 매도")
    markets_by_symbol: dict[str, str] = {}

    krw_cash = 0.0
    holdings: dict[str, float] = {}
    balances_by_currency: dict[str, dict] = {}

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
        krw_market = f"KRW-{cur}"
        if krw_market not in allowed_markets:
            continue
        holdings[krw_market] = total
        balances_by_currency[cur] = bal

    tickers = await upbit_client.tickers(list(holdings.keys()))
    new_positions: dict[str, Position] = {}
    upbit_rows: list[UpbitHoldingRow] = []
    synced_at = time.time()

    for krw_market, total_qty in holdings.items():
        t = tickers.get(krw_market)
        if not t:
            continue
        price_krw = float(t.get("trade_price", 0))
        if price_krw <= 0:
            continue
        price_usdt = price_krw / portfolio.usdt_krw
        symbol = upbit_to_symbol(krw_market)
        base = krw_market.replace("KRW-", "")
        markets_by_symbol[symbol.upper()] = krw_market
        pm = meta_map.get(symbol, {})

        auto_q = min(float(pm.get("auto_quantity", 0)), total_qty)
        manual_q = max(0.0, total_qty - auto_q)
        if pm.get("excluded_from_auto"):
            manual_q = total_qty
            auto_q = 0.0
        if abs(auto_q + manual_q - total_qty) > 1e-8:
            manual_q = total_qty
            auto_q = 0.0

        bal = balances_by_currency.get(base, {})
        avg_buy_krw = _parse_avg_buy_krw(bal)
        auto_cost, man_cost, auto_avg, manual_avg = _resolve_position_costs(
            pm,
            total_qty=total_qty,
            auto_q=auto_q,
            manual_q=manual_q,
            avg_buy_krw=avg_buy_krw,
            price_krw=price_krw,
            usdt_krw=portfolio.usdt_krw,
        )
        ref_usdt = auto_avg or manual_avg or price_usdt
        cost_krw = auto_cost + man_cost
        valuation_krw = total_qty * price_krw

        cm = coin_meta(symbol, base)
        custom_sl = bool(pm.get("custom_sl_tp", False))
        sl_pct_meta = float(pm.get("custom_stop_loss_pct", 0))
        tp_pct_meta = float(pm.get("custom_take_profit_pct", 0))
        sl = float(pm.get("stop_loss", 0))
        tp = float(pm.get("take_profit", 0))
        if not custom_sl and total_qty > 0 and sl <= 0:
            sl = ref_usdt * (1 - config.stop_loss_pct / 100)
            tp = ref_usdt * (1 + config.take_profit_pct / 100)
        elif custom_sl and total_qty > 0 and ref_usdt > 0:
            if sl_pct_meta > 0:
                sl = ref_usdt * (1 - sl_pct_meta / 100)
            elif sl <= 0:
                sl = ref_usdt * (1 - config.stop_loss_pct / 100)
            if tp_pct_meta > 0:
                tp = ref_usdt * (1 + tp_pct_meta / 100)
            elif tp <= 0:
                tp = ref_usdt * (1 + config.take_profit_pct / 100)

        pos = Position(
            symbol=symbol,
            base=cm["base"],
            name_ko=cm["name_ko"],
            name_en=cm["name_en"],
            pair_label=cm["pair_label"],
            display=cm["display"],
            auto_quantity=auto_q,
            manual_quantity=manual_q,
            avg_price=ref_usdt,
            auto_avg_price=auto_avg,
            manual_avg_price=manual_avg,
            current_price=price_usdt,
            stop_loss=sl,
            take_profit=tp,
            trailing_high=float(pm.get("trailing_high", price_usdt)),
            opened_at=float(pm.get("opened_at", time.time())),
            score=float(pm.get("score", 0)),
            cost_basis_krw=cost_krw,
            auto_cost_basis_krw=auto_cost,
            manual_cost_basis_krw=man_cost,
            entry_reason=pm.get("entry_reason", "업비트 동기화"),
            entry_score=float(pm.get("entry_score", 0)),
            entry_outlook=pm.get("entry_outlook", ""),
            excluded_from_auto=bool(pm.get("excluded_from_auto", False)),
            custom_sl_tp=custom_sl,
            custom_stop_loss_pct=sl_pct_meta if custom_sl else 0.0,
            custom_take_profit_pct=tp_pct_meta if custom_sl else 0.0,
            data_source="upbit",
            exchange_quantity=total_qty,
            avg_buy_price_krw=avg_buy_krw,
            current_price_krw=price_krw,
            valuation_krw=valuation_krw,
        )
        if total_qty > 1e-10:
            new_positions[symbol] = pos
            upbit_rows.append(
                UpbitHoldingRow(
                    symbol=symbol,
                    market=krw_market,
                    currency=base,
                    quantity=total_qty,
                    avg_buy_price_krw=avg_buy_krw,
                    current_price_krw=price_krw,
                    valuation_krw=valuation_krw,
                    cost_basis_krw=cost_krw,
                )
            )

    portfolio.positions = new_positions
    portfolio.cash_krw = krw_cash
    portfolio.realized_pnl_krw = float(live_meta.get("realized_pnl_krw", 0))

    portfolio.trades = merge_trade_events(
        portfolio.trades,
        live_meta.get("trades", [])[-100:],
        usdt_krw=portfolio.usdt_krw,
        limit=100,
    )

    new_qty = {
        sym: float(pos.exchange_quantity or pos.quantity)
        for sym, pos in new_positions.items()
    }
    await backfill_recent_sells(
        portfolio,
        live_meta,
        upbit_client,
        prev_qty=prev_qty,
        new_qty=new_qty,
        markets_by_symbol=markets_by_symbol,
        pending_reasons=pending_reasons,
    )
    live_meta["trades"] = merge_trade_dicts(
        live_meta.get("trades", [])[-100:],
        [t.model_dump() for t in portfolio.trades],
        usdt_krw=portfolio.usdt_krw,
        limit=100,
    )

    n = len(new_positions)
    coin_value = sum(p.valuation_krw for p in new_positions.values())
    invested_principal = sum(
        (p.avg_buy_price_krw * p.exchange_quantity)
        if p.avg_buy_price_krw > 0
        else p.cost_basis_krw
        for p in new_positions.values()
    )
    total_krw = portfolio.cash_krw + coin_value

    snap = UpbitAccountSnapshot(
        synced_at=synced_at,
        krw_balance=krw_cash,
        coin_valuation_krw=coin_value,
        total_assets_krw=total_krw,
        invested_principal_krw=invested_principal,
        holdings=sorted(upbit_rows, key=lambda r: r.valuation_krw, reverse=True),
    )
    live_meta["upbit_snapshot"] = snap.model_dump()
    live_meta["account_principal_krw"] = invested_principal

    return (
        f"[업비트 API] 보유 {n}종 · 총자산 {total_krw:,.0f}원 "
        f"(코인 {coin_value:,.0f} + KRW {krw_cash:,.0f}) · 투자원금 {invested_principal:,.0f}원"
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
    tickers = await upbit_feed.tickers_24h()
    portfolio.usdt_krw = await upbit_feed.usdt_krw_rate()
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

    portfolio.trades = merge_trade_events(
        portfolio.trades,
        live_meta.get("trades", [])[-100:],
        usdt_krw=portfolio.usdt_krw,
        limit=100,
    )

    n = len(new_positions)
    total_krw = portfolio.cash_krw + sum(
        portfolio.usdt_to_krw(p.quantity * p.current_price)
        for p in new_positions.values()
    )
    if not live_meta.get("account_principal_krw"):
        live_meta["account_principal_krw"] = total_krw
    net = "테스트넷" if getattr(config, "use_testnet", False) else "실거래"
    return f"[Binance {net}] 연동 · 보유 {n}종 · 총자산 {total_krw:,.0f}원 (USDT {usdt_free:.2f})"


def export_live_meta(portfolio, preserve: dict[str, Any] | None = None) -> dict[str, Any]:
    """포트폴리오 → AIDI 메타 저장 (잔고 제외). preserve: account_principal 등 유지."""
    prev_map: dict = (preserve or {}).get("positions_meta") or {}
    positions_meta = {}
    for sym, pos in portfolio.positions.items():
        prev = prev_map.get(sym, {}) if isinstance(prev_map.get(sym), dict) else {}
        row = {
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
            "custom_sl_tp": pos.custom_sl_tp,
            "custom_stop_loss_pct": pos.custom_stop_loss_pct,
            "custom_take_profit_pct": pos.custom_take_profit_pct,
        }
        if prev.get("pending_exit"):
            row["pending_exit"] = prev["pending_exit"]
        positions_meta[sym] = row
    prev_trades = (preserve or {}).get("trades") or []
    merged_trades = merge_trade_dicts(
        prev_trades,
        [t.model_dump() for t in portfolio.trades],
        usdt_krw=max(getattr(portfolio, "usdt_krw", 0), 1.0),
        limit=100,
    )
    out: dict[str, Any] = {
        "positions_meta": positions_meta,
        "trades": merged_trades,
        "realized_pnl_krw": portfolio.realized_pnl_krw,
    }
    if preserve:
        if preserve.get("account_principal_krw"):
            out["account_principal_krw"] = preserve["account_principal_krw"]
        if preserve.get("upbit_snapshot"):
            out["upbit_snapshot"] = preserve["upbit_snapshot"]
    return out

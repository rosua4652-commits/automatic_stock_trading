from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, is_dataclass
from typing import Any

from .ai_client import AIAnalysisClient
from .config import AppConfig
from .indicators import percent_change
from .portfolio import PortfolioManager
from .reporting import build_portfolio_report
from .runner import BotController, TradingBot
from .simulator import PaperBroker, summarize_trades
from .storage import append_jsonl
from .strategy import MarketContext, ScalpingStrategy
from .upbit import UpbitClient, UpbitError
from .web import serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upbit AI-assisted scalping toolkit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("accounts", help="Test private API access by listing account currencies")

    portfolio_parser = subparsers.add_parser("portfolio", help="Value account balances and print portfolio statistics")
    portfolio_parser.add_argument("--save", action="store_true", help="Append a snapshot to logs/portfolio.jsonl")

    report_parser = subparsers.add_parser("report", help="Generate an HTML portfolio report from saved snapshots")
    report_parser.add_argument("--output", default="reports/portfolio.html")

    scan_parser = subparsers.add_parser("scan", help="Scan KRW markets and rank scalping candidates")
    scan_parser.add_argument("--limit", type=int, default=10)
    scan_parser.add_argument("--ai", action="store_true", help="Request AI analysis for the top signal")

    backtest_parser = subparsers.add_parser("backtest", help="Run a simple candle-window simulation for one market")
    backtest_parser.add_argument("--market", required=True, help="Example: KRW-BTC")
    backtest_parser.add_argument("--unit", type=int, default=5)
    backtest_parser.add_argument("--count", type=int, default=200)

    live_parser = subparsers.add_parser("live-once", help="Place one guarded live buy for the best current signal")
    live_parser.add_argument("--i-understand-live-risk", action="store_true")

    run_parser = subparsers.add_parser("run", help="Continuously analyze and paper/live trade until stopped")
    run_parser.add_argument("--mode", choices=["paper", "live"], default="paper")
    run_parser.add_argument("--interval", type=int, default=60)

    web_parser = subparsers.add_parser("web", help="Start the built-in web dashboard")
    web_parser.add_argument("--host", default="0.0.0.0")
    web_parser.add_argument("--port", type=int, default=8080)
    web_parser.add_argument("--interval", type=int, default=60)

    args = parser.parse_args(argv)
    config = AppConfig.from_env()
    client = UpbitClient(config.credentials)

    try:
        if args.command == "accounts":
            return _accounts(client)
        if args.command == "portfolio":
            return _portfolio(config, client, args.save)
        if args.command == "report":
            return _report(args.output)
        if args.command == "scan":
            return _scan(config, client, args.limit, args.ai)
        if args.command == "backtest":
            return _backtest(config, client, args.market, args.unit, args.count)
        if args.command == "live-once":
            return _live_once(config, client, args.i_understand_live_risk)
        if args.command == "run":
            return _run(config, client, args.mode, args.interval)
        if args.command == "web":
            serve(args.host, args.port, args.interval)
            return 0
    except UpbitError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 1


def _accounts(client: UpbitClient) -> int:
    rows = client.get_accounts()
    safe_rows = [
        {"currency": row.get("currency"), "balance": row.get("balance"), "locked": row.get("locked")}
        for row in rows
    ]
    print_json({"ok": True, "accounts": safe_rows})
    return 0


def _portfolio(config: AppConfig, client: UpbitClient, save: bool) -> int:
    snapshot = PortfolioManager(client, config.quote_currency).snapshot()
    if save:
        append_jsonl("logs/portfolio.jsonl", {"snapshot": snapshot})
    print_json({"ok": True, "saved": save, "snapshot": snapshot})
    return 0


def _report(output: str) -> int:
    path = build_portfolio_report(output_path=output)
    print_json({"ok": True, "report": str(path)})
    return 0


def _scan(config: AppConfig, client: UpbitClient, limit: int, use_ai: bool) -> int:
    signals = _rank_signals(config, client)
    top = signals[:limit]
    output: dict[str, Any] = {"ok": True, "signals": top}

    if use_ai and top:
        ai_client = AIAnalysisClient(config)
        output["ai_analysis"] = ai_client.summarize_signal(top[0], {"source": "scan"})

    append_jsonl("logs/scans.jsonl", {"signals": top})
    print_json(output)
    return 0


def _backtest(config: AppConfig, client: UpbitClient, market: str, unit: int, count: int) -> int:
    candles = client.get_minute_candles(market, unit=unit, count=count)
    strategy = ScalpingStrategy(config.risk)
    broker = PaperBroker(config.risk)
    trades = []

    for index in range(80, len(candles) - 6):
        window = candles[: index + 1]
        context = _btc_context(config, client)
        signal = strategy.evaluate(market, window, context)
        if not signal.should_enter or not signal.plan:
            continue
        trade = broker.simulate_position(signal.plan, candles[index + 1 : index + 7])
        if trade:
            trades.append(trade)

    result = summarize_trades(trades)
    append_jsonl("logs/backtests.jsonl", {"market": market, "result": result})
    print_json({"ok": True, "market": market, "result": result})
    return 0


def _live_once(config: AppConfig, client: UpbitClient, confirmed: bool) -> int:
    if not config.live_trading_enabled or config.trading_mode != "live":
        print_json({"ok": False, "error": "Live trading is disabled. Set TRADING_MODE=live and LIVE_TRADING_ENABLED=true."})
        return 3
    if not confirmed:
        print_json({"ok": False, "error": "Pass --i-understand-live-risk to place a live order."})
        return 3

    signals = _rank_signals(config, client)
    signal = next((item for item in signals if item.should_enter and item.plan), None)
    if signal is None or signal.plan is None:
        print_json({"ok": False, "error": "No valid live entry signal"})
        return 0

    response = client.place_market_buy(signal.plan.market, signal.plan.budget_krw)
    append_jsonl("logs/live_orders.jsonl", {"signal": signal, "response": response})
    print_json({"ok": True, "signal": signal, "order": response})
    return 0


def _run(config: AppConfig, client: UpbitClient, mode: str, interval: int) -> int:
    controller = BotController(TradingBot(config, client), interval_seconds=interval)
    controller.start(mode)
    print_json({"ok": True, "message": "bot started; press Ctrl+C or create data/STOP_BOT to stop", "status": controller.status()})
    try:
        while controller.is_running:
            time.sleep(interval)
    except KeyboardInterrupt:
        controller.stop()
        print_json({"ok": True, "message": "bot stopping", "status": controller.status()})
    return 0


def _rank_signals(config: AppConfig, client: UpbitClient) -> list[Any]:
    markets = client.get_markets(config.quote_currency)
    tickers = client.get_tickers(markets)
    liquid_markets = [
        row["market"]
        for row in sorted(tickers, key=lambda item: item.get("acc_trade_price_24h", 0), reverse=True)
        if float(row.get("acc_trade_price_24h", 0)) >= config.min_24h_trade_price_krw
    ][: config.scan_top_markets]

    context = _btc_context(config, client)
    strategy = ScalpingStrategy(config.risk)
    signals = []
    for market in liquid_markets:
        try:
            candles = client.get_minute_candles(market, unit=5, count=120)
        except UpbitError:
            continue
        signals.append(strategy.evaluate(market, candles, context))
    return sorted(signals, key=lambda signal: signal.score, reverse=True)


def _btc_context(config: AppConfig, client: UpbitClient) -> MarketContext:
    try:
        btc = client.get_minute_candles(f"{config.quote_currency}-BTC", unit=5, count=2)
        change = percent_change(btc[0].trade_price, btc[-1].trade_price) if len(btc) >= 2 else 0.0
    except UpbitError:
        change = 0.0
    return MarketContext(btc_5m_change_pct=change)


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2))


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())

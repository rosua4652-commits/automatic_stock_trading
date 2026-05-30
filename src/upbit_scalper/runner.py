from __future__ import annotations

import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import AppConfig
from .indicators import percent_change
from .portfolio import PortfolioManager
from .state import BotPosition, BotState, StateStore
from .storage import append_jsonl
from .strategy import MarketContext, ScalpingStrategy, Signal
from .upbit import UpbitClient, UpbitError


class TradingBot:
    """Continuous analysis/trading loop.

    Default mode is paper trading. Live trading requires both config flags and
    an explicit start mode of "live".
    """

    def __init__(self, config: AppConfig, client: UpbitClient | None = None, state_store: StateStore | None = None) -> None:
        self.config = config
        self.client = client or UpbitClient(config.credentials)
        self.state_store = state_store or StateStore()
        self.strategy = ScalpingStrategy(config.risk)

    def step(self, requested_mode: str = "paper") -> dict[str, Any]:
        state = self.state_store.load()
        mode = self._effective_mode(requested_mode)

        event: dict[str, Any] = {
            "mode": mode,
            "state": asdict(state),
        }

        if state.position:
            event.update(self._manage_position(state, mode))
        else:
            signal = self.best_signal()
            event["signal"] = signal
            if signal.should_enter and signal.plan:
                event.update(self._open_position(state, signal, mode))
            else:
                event["decision"] = "watch"

        self.state_store.save(state)
        append_jsonl("logs/bot_events.jsonl", event)
        return event

    def best_signal(self) -> Signal:
        signals = self.rank_signals()
        if not signals:
            raise UpbitError("No scan signals were produced")
        return signals[0]

    def rank_signals(self) -> list[Signal]:
        markets = self.client.get_markets(self.config.quote_currency)
        tickers = self.client.get_tickers(markets)
        liquid_markets = [
            row["market"]
            for row in sorted(tickers, key=lambda item: item.get("acc_trade_price_24h", 0), reverse=True)
            if float(row.get("acc_trade_price_24h", 0)) >= self.config.min_24h_trade_price_krw
        ][: self.config.scan_top_markets]

        context = self.market_context()
        signals: list[Signal] = []
        for market in liquid_markets:
            try:
                candles = self.client.get_minute_candles(market, unit=5, count=120)
            except UpbitError:
                continue
            signals.append(self.strategy.evaluate(market, candles, context))
        return sorted(signals, key=lambda signal: signal.score, reverse=True)

    def market_context(self) -> MarketContext:
        try:
            btc = self.client.get_minute_candles(f"{self.config.quote_currency}-BTC", unit=5, count=2)
            change = percent_change(btc[0].trade_price, btc[-1].trade_price) if len(btc) >= 2 else 0.0
        except UpbitError:
            change = 0.0
        return MarketContext(btc_5m_change_pct=change)

    def portfolio_snapshot(self) -> dict[str, Any]:
        snapshot = PortfolioManager(self.client, self.config.quote_currency).snapshot()
        append_jsonl("logs/portfolio.jsonl", {"snapshot": snapshot})
        return asdict(snapshot)

    def _open_position(self, state: BotState, signal: Signal, mode: str) -> dict[str, Any]:
        plan = signal.plan
        if plan is None:
            return {"decision": "watch", "reason": "missing plan"}

        volume = plan.budget_krw / plan.entry_price
        if mode == "live":
            response = self.client.place_market_buy(plan.market, plan.budget_krw)
            append_jsonl("logs/live_orders.jsonl", {"side": "buy", "signal": signal, "response": response})
            volume = float(response.get("executed_volume") or response.get("volume") or volume)

        state.position = BotPosition(
            market=plan.market,
            entry_price=plan.entry_price,
            volume=volume,
            budget_krw=plan.budget_krw,
            take_profit_price=plan.take_profit_price,
            stop_loss_price=plan.stop_loss_price,
            trailing_stop_pct=plan.trailing_stop_pct,
            highest_price=plan.entry_price,
            opened_at=datetime.now(timezone.utc).isoformat(),
            mode=mode,
        )
        return {"decision": "open_position", "position": asdict(state.position)}

    def _manage_position(self, state: BotState, mode: str) -> dict[str, Any]:
        position = state.position
        if position is None:
            return {"decision": "watch"}

        ticker = self.client.get_tickers([position.market])[0]
        current_price = float(ticker["trade_price"])
        position.highest_price = max(position.highest_price, current_price)
        trailing_stop_price = position.highest_price * (1 - position.trailing_stop_pct / 100)

        reason = None
        if current_price >= position.take_profit_price:
            reason = "take_profit"
        elif current_price <= position.stop_loss_price:
            reason = "stop_loss"
        elif current_price <= trailing_stop_price and position.highest_price > position.entry_price:
            reason = "trailing_stop"

        gross_pct = ((current_price - position.entry_price) / position.entry_price) * 100
        net_pct = gross_pct - self.config.risk.round_trip_cost_pct
        unrealized_pnl = position.budget_krw * (net_pct / 100)

        if reason is None:
            return {
                "decision": "hold_position",
                "current_price": current_price,
                "unrealized_pnl_krw": unrealized_pnl,
                "unrealized_pnl_pct": net_pct,
                "trailing_stop_price": trailing_stop_price,
            }

        if mode == "live":
            response = self.client.place_market_sell(position.market, position.volume)
            append_jsonl("logs/live_orders.jsonl", {"side": "sell", "position": asdict(position), "response": response})

        state.realized_pnl_krw += unrealized_pnl
        state.consecutive_losses = state.consecutive_losses + 1 if unrealized_pnl < 0 else 0
        closed = asdict(position)
        state.position = None
        return {
            "decision": "close_position",
            "reason": reason,
            "closed_position": closed,
            "exit_price": current_price,
            "realized_pnl_krw": unrealized_pnl,
            "realized_pnl_pct": net_pct,
        }

    def _effective_mode(self, requested_mode: str) -> str:
        requested = requested_mode.strip().lower()
        if requested != "live":
            return "paper"
        if self.config.trading_mode == "live" and self.config.live_trading_enabled:
            return "live"
        return "paper"


class BotController:
    def __init__(self, bot: TradingBot, interval_seconds: int = 60, stop_file: str = "data/STOP_BOT") -> None:
        self.bot = bot
        self.interval_seconds = interval_seconds
        self.stop_file = Path(stop_file)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.last_event: dict[str, Any] | None = None
        self.last_error: str | None = None
        self.started_at: str | None = None
        self.mode = "paper"

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, mode: str = "paper") -> bool:
        if self.is_running:
            return False
        self.mode = mode
        self._stop_event.clear()
        if self.stop_file.exists():
            self.stop_file.unlink()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        self.stop_file.parent.mkdir(parents=True, exist_ok=True)
        self.stop_file.write_text("stop\n", encoding="utf-8")

    def status(self) -> dict[str, Any]:
        return {
            "running": self.is_running,
            "mode": self.mode,
            "interval_seconds": self.interval_seconds,
            "started_at": self.started_at,
            "last_event": self.last_event,
            "last_error": self.last_error,
        }

    def configure(self, bot: TradingBot, interval_seconds: int | None = None) -> None:
        with self._lock:
            self.bot = bot
            if interval_seconds is not None:
                self.interval_seconds = interval_seconds

    def _run_loop(self) -> None:
        while not self._stop_event.is_set() and not self.stop_file.exists():
            try:
                event = self.bot.step(self.mode)
                with self._lock:
                    self.last_event = event
                    self.last_error = None
            except Exception as exc:  # Log and keep the process alive for transient API/network failures.
                error = f"{type(exc).__name__}: {exc}"
                append_jsonl("logs/errors.jsonl", {"error": error})
                with self._lock:
                    self.last_error = error
            self._stop_event.wait(self.interval_seconds)

"""모의·실거래 포트폴리오 완전 분리."""

import asyncio

from app.engine.portfolio import PortfolioManager
from app.engine.live_sync import (
    export_live_meta,
    refresh_live_position_prices,
    sync_live_portfolio,
)
from app.models import AppConfig, TradeMode
from app.storage.credentials import has_api_keys
from app.storage.persistence import (
    load_live_meta,
    load_paper_state,
    save_live_meta,
    save_paper_state,
)


class PortfolioStore:
    def __init__(self) -> None:
        self.paper = PortfolioManager()
        self.live = PortfolioManager()
        self._live_meta: dict = load_live_meta()
        self._lock = asyncio.Lock()
        self._load_paper()

    def _load_paper(self) -> None:
        data = load_paper_state()
        if not data:
            return
        self.paper.cash_krw = float(data.get("cash_krw", self.paper.cash_krw))
        self.paper.realized_pnl_krw = float(data.get("realized_pnl_krw", 0))
        self.paper.usdt_krw = float(data.get("usdt_krw", 1350))
        from app.models import Position, TradeEvent

        self.paper.positions = {}
        for sym, pd in data.get("positions", {}).items():
            try:
                self.paper.positions[sym] = Position(**pd)
            except Exception:
                continue
        trades = data.get("trades", [])
        self.paper.trades = []
        for t in trades:
            try:
                self.paper.trades.append(TradeEvent(**t))
            except Exception:
                continue

    def reset_paper(self, initial_balance_krw: float) -> None:
        from app.storage.persistence import reset_paper_state

        self.paper = PortfolioManager()
        self.paper.cash_krw = float(initial_balance_krw)
        self.paper.realized_pnl_krw = 0.0
        self.paper.positions = {}
        self.paper.trades = []
        reset_paper_state(initial_balance_krw)

    def save_paper(self) -> None:
        from app.models import Position

        save_paper_state(
            {
                "cash_krw": self.paper.cash_krw,
                "realized_pnl_krw": self.paper.realized_pnl_krw,
                "usdt_krw": self.paper.usdt_krw,
                "positions": {
                    s: p.model_dump() for s, p in self.paper.positions.items()
                },
                "trades": [t.model_dump() for t in self.paper.trades[-200:]],
            }
        )

    def save_live_meta(self) -> None:
        prev = self._live_meta
        self._live_meta = export_live_meta(self.live, preserve=prev)
        save_live_meta(self._live_meta)

    def get(self, mode: TradeMode) -> PortfolioManager:
        return self.paper if mode == TradeMode.PAPER else self.live

    async def sync_live(
        self, config: AppConfig, *, fetch_trades: bool = True
    ) -> str:
        async with self._lock:
            prev = self._live_meta
            if prev.get("trades_force_sync"):
                fetch_trades = True
            msg = await sync_live_portfolio(
                self.live, config, prev, fetch_trades=fetch_trades
            )
            self._live_meta = export_live_meta(self.live, preserve=prev)
            save_live_meta(self._live_meta)
            return msg

    async def refresh_live_prices(self, config: AppConfig) -> str:
        """보유 종목 시세만 빠르게 갱신 (체결 내역 API 없음)."""
        async with self._lock:
            return await refresh_live_position_prices(self.live, config)

    async def on_mode_change(
        self, old: TradeMode, new: TradeMode, config: AppConfig
    ) -> str:
        if old == new:
            return ""
        if old == TradeMode.PAPER:
            self.save_paper()
        elif old == TradeMode.LIVE:
            self.save_live_meta()

        if new == TradeMode.LIVE:
            if not has_api_keys(config):
                return "실거래: API 키를 입력하세요"
            self.live = PortfolioManager()
            self.live.positions = {}
            self.live.trades = []
            self.live.cash_krw = 0
            self._live_meta["trades_force_sync"] = True
            return await self.sync_live(config)
        else:
            self._load_paper()
            return "모의투자 데이터로 전환 (실거래와 분리됨)"

    def persist_active(self, mode: TradeMode) -> None:
        if mode == TradeMode.PAPER:
            self.save_paper()
        else:
            self.save_live_meta()


store = PortfolioStore()

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, computed_field


class BotStatus(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"


class AppConfig(BaseModel):
    target_profit_krw: float = Field(default=2_000_000, ge=100_000, le=1_000_000_000)


class Position(BaseModel):
    symbol: str
    quantity: float
    avg_price: float
    current_price: float = 0.0
    stop_loss: float
    take_profit: float
    trailing_high: float = 0.0
    opened_at: float
    score: float = 0.0

    @computed_field
    @property
    def value(self) -> float:
        return self.quantity * self.current_price

    @computed_field
    @property
    def pnl(self) -> float:
        return (self.current_price - self.avg_price) * self.quantity

    @computed_field
    @property
    def pnl_pct(self) -> float:
        if self.avg_price <= 0:
            return 0.0
        return (self.current_price - self.avg_price) / self.avg_price * 100


class PortfolioSnapshot(BaseModel):
    cash_krw: float
    total_value_krw: float
    invested_krw: float
    unrealized_pnl_krw: float
    realized_pnl_krw: float
    profit_toward_target_krw: float
    target_profit_krw: float
    progress_pct: float
    positions: list[Position]


class CoinCandidate(BaseModel):
    symbol: str
    base: str
    score: float
    trend: str
    rsi: float
    change_24h: float
    volume_usdt: float
    reason: str


class TradeEvent(BaseModel):
    ts: float
    symbol: str
    side: str
    price: float
    quantity: float
    reason: str


class BotState(BaseModel):
    status: BotStatus = BotStatus.STOPPED
    selected_symbol: str = "BTCUSDT"
    last_scan: Optional[float] = None
    message: str = "대기 중"
    candidates: list[CoinCandidate] = Field(default_factory=list)
    recent_trades: list[TradeEvent] = Field(default_factory=list)


class Candle(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class StatusResponse(BaseModel):
    bot: BotState
    portfolio: PortfolioSnapshot
    config: AppConfig

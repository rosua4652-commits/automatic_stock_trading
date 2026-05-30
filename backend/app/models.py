from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, computed_field, field_validator


class BotStatus(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    STOPPING = "stopping"


class TradeMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class AppConfig(BaseModel):
    trade_mode: TradeMode = TradeMode.PAPER
    target_profit_krw: float = Field(default=2_000_000, ge=100_000, le=1_000_000_000)
    initial_balance_krw: float = Field(default=10_000_000, ge=100_000, le=1_000_000_000)
    max_positions: int = Field(default=6, ge=1, le=15)
    stop_loss_pct: float = Field(default=6.0, ge=1.0, le=25.0)
    take_profit_pct: float = Field(default=12.0, ge=2.0, le=50.0)
    scan_interval_sec: int = Field(default=45, ge=15, le=300)
    min_buy_score: float = Field(default=40.0, ge=20.0, le=90.0)
    min_entry_score: float = Field(default=60.0, ge=40.0, le=90.0)
    binance_api_key: str = ""
    binance_api_secret: str = ""

    @field_validator("binance_api_key", "binance_api_secret", mode="before")
    @classmethod
    def strip_secrets(cls, v):
        return (v or "").strip()


class CoinMeta(BaseModel):
    symbol: str
    base: str
    quote: str = "USDT"
    name_ko: str
    name_en: str
    pair_label: str
    display: str


class Position(BaseModel):
    symbol: str
    base: str
    name_ko: str
    name_en: str
    pair_label: str
    display: str
    quantity: float
    avg_price: float
    current_price: float = 0.0
    stop_loss: float
    take_profit: float
    trailing_high: float = 0.0
    opened_at: float
    score: float = 0.0
    cost_basis_krw: float = 0.0
    entry_reason: str = ""
    entry_score: float = 0.0
    entry_outlook: str = ""
    auto_managed: bool = True

    @computed_field
    @property
    def value_usdt(self) -> float:
        return self.quantity * self.current_price

    @computed_field
    @property
    def pnl_usdt(self) -> float:
        return (self.current_price - self.avg_price) * self.quantity

    @computed_field
    @property
    def pnl_pct(self) -> float:
        if self.avg_price <= 0:
            return 0.0
        return (self.current_price - self.avg_price) / self.avg_price * 100

    # KRW 환산은 snapshot 시 portfolio에서 채움
    current_value_krw: float = 0.0
    pnl_krw: float = 0.0
    weight_pct: float = 0.0


class PortfolioSnapshot(BaseModel):
    cash_krw: float
    total_value_krw: float
    invested_krw: float
    principal_krw: float
    unrealized_pnl_krw: float
    realized_pnl_krw: float
    profit_toward_target_krw: float
    target_profit_krw: float
    progress_pct: float
    positions: list[Position]


class CoinCandidate(BaseModel):
    symbol: str
    base: str
    name_ko: str
    name_en: str
    pair_label: str
    display: str
    score: float
    trend: str
    rsi: float
    change_24h: float
    volume_usdt: float
    reason: str
    entry_score: float = 0.0
    entry_ok: bool = False
    entry_outlook: str = ""


class TradeEvent(BaseModel):
    ts: float
    symbol: str
    base: str
    display: str
    side: str
    price: float
    quantity: float
    amount_krw: float
    amount_usdt: float
    reason: str


class CoinView(BaseModel):
    meta: CoinMeta
    price_usdt: float = 0.0
    change_24h: float = 0.0
    in_portfolio: bool = False
    position: Optional[Position] = None
    candidate: Optional[CoinCandidate] = None


class BotState(BaseModel):
    status: BotStatus = BotStatus.STOPPED
    view_symbol: str = "BTCUSDT"
    last_scan: Optional[float] = None
    message: str = "대기 중"
    candidates: list[CoinCandidate] = Field(default_factory=list)
    recent_trades: list[TradeEvent] = Field(default_factory=list)
    manual_mode: bool = True


class ManualBuyRequest(BaseModel):
    symbol: str
    amount_krw: float = Field(ge=50_000, le=500_000_000)


class ManualSellRequest(BaseModel):
    symbol: str
    percent: float = Field(default=100.0, ge=1.0, le=100.0)


class StatusResponse(BaseModel):
    bot: BotState
    portfolio: PortfolioSnapshot
    config: AppConfig
    view: CoinView
    tabs: list[str] = Field(default_factory=list)

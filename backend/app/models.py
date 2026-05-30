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
    max_positions: int = Field(
        default=0,
        ge=0,
        le=30,
        description="0이면 보유 코인 수 제한 없음",
    )
    stop_loss_pct: float = Field(default=6.0, ge=1.0, le=25.0)
    take_profit_pct: float = Field(default=12.0, ge=2.0, le=50.0)
    scan_interval_sec: int = Field(default=45, ge=15, le=300)
    min_buy_score: float = Field(default=40.0, ge=20.0, le=90.0)
    min_entry_score: float = Field(default=60.0, ge=40.0, le=90.0)
    exchange: str = Field(default="upbit", description="upbit | binance")
    api_access_key: str = ""
    api_secret_key: str = ""
    binance_api_key: str = ""
    binance_api_secret: str = ""
    use_testnet: bool = False

    @field_validator(
        "api_access_key",
        "api_secret_key",
        "binance_api_key",
        "binance_api_secret",
        mode="before",
    )
    @classmethod
    def strip_secrets(cls, v):
        return (v or "").strip()

    def model_post_init(self, __context) -> None:
        if self.binance_api_key and not self.api_access_key:
            object.__setattr__(self, "api_access_key", self.binance_api_key)
        if self.binance_api_secret and not self.api_secret_key:
            object.__setattr__(self, "api_secret_key", self.binance_api_secret)
        if self.api_access_key and not self.binance_api_key:
            object.__setattr__(self, "binance_api_key", self.api_access_key)
        if self.api_secret_key and not self.binance_api_secret:
            object.__setattr__(self, "binance_api_secret", self.api_secret_key)


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
    # 총 수량 = auto + manual
    auto_quantity: float = 0.0
    manual_quantity: float = 0.0
    avg_price: float = 0.0
    auto_avg_price: float = 0.0
    manual_avg_price: float = 0.0
    current_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    trailing_high: float = 0.0
    opened_at: float = 0.0
    score: float = 0.0
    cost_basis_krw: float = 0.0
    auto_cost_basis_krw: float = 0.0
    manual_cost_basis_krw: float = 0.0
    entry_reason: str = ""
    entry_score: float = 0.0
    entry_outlook: str = ""
    excluded_from_auto: bool = False

    @computed_field
    @property
    def quantity(self) -> float:
        return self.auto_quantity + self.manual_quantity

    @computed_field
    @property
    def value_usdt(self) -> float:
        return self.quantity * self.current_price

    @computed_field
    @property
    def auto_value_usdt(self) -> float:
        return self.auto_quantity * self.current_price

    @computed_field
    @property
    def pnl_pct(self) -> float:
        if self.avg_price <= 0:
            return 0.0
        return (self.current_price - self.avg_price) / self.avg_price * 100

    @computed_field
    @property
    def auto_pnl_pct(self) -> float:
        if self.auto_avg_price <= 0 or self.auto_quantity <= 0:
            return 0.0
        return (self.current_price - self.auto_avg_price) / self.auto_avg_price * 100

    current_value_krw: float = 0.0
    auto_value_krw: float = 0.0
    manual_value_krw: float = 0.0
    pnl_krw: float = 0.0
    auto_pnl_krw: float = 0.0
    manual_pnl_krw: float = 0.0
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
    entry_pattern: str = ""
    entry_detail: str = ""
    entry_reasons: list[str] = Field(default_factory=list)


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
    is_auto: bool = True


class ChartMarker(BaseModel):
    time: int
    price: float
    side: str
    text: str
    is_auto: bool = True


class CoinView(BaseModel):
    meta: CoinMeta
    price_usdt: float = 0.0
    change_24h: float = 0.0
    in_portfolio: bool = False
    position: Optional[Position] = None
    candidate: Optional[CoinCandidate] = None


class InvestmentRecommendation(BaseModel):
    symbol: str
    base: str
    name_ko: str
    display: str
    pair_label: str
    market_score: float = 0.0
    entry_score: float = 0.0
    weight_pct: float = 0.0
    amount_krw: float = 0.0
    entry_detail: str = ""
    change_24h: float = 0.0
    trend: str = ""
    selected: bool = True


class ApplyRecommendationsRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list, description="비우면 선택된 항목 전체")


class BotState(BaseModel):
    status: BotStatus = BotStatus.STOPPED
    view_symbol: str = "BTCUSDT"
    last_scan: Optional[float] = None
    message: str = "대기 중"
    candidates: list[CoinCandidate] = Field(default_factory=list)
    recommendations: list[InvestmentRecommendation] = Field(default_factory=list)
    recent_trades: list[TradeEvent] = Field(default_factory=list)
    manual_mode: bool = True


class ManualBuyRequest(BaseModel):
    symbol: str
    amount_krw: float = Field(ge=50_000, le=500_000_000)


class ManualSellRequest(BaseModel):
    symbol: str
    percent: float = Field(default=100.0, ge=1.0, le=100.0)
    from_auto_only: bool = False


class PositionExcludeRequest(BaseModel):
    exclude: bool


class AccountLinkInfo(BaseModel):
    linked: bool = False
    mode: str = "paper"
    message: str = ""
    last_sync: Optional[float] = None
    total_assets_krw: Optional[float] = None
    cash_krw: Optional[float] = None
    exchange: str = ""


class StatusResponse(BaseModel):
    bot: BotState
    portfolio: PortfolioSnapshot
    config: AppConfig
    view: CoinView
    tabs: list[str] = Field(default_factory=list)
    account_link: AccountLinkInfo = Field(default_factory=AccountLinkInfo)

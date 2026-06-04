from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator


class BotStatus(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    STOPPING = "stopping"


class TradeMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class AutoExitStrength(str, Enum):
    WEAK = "weak"
    MEDIUM = "medium"
    STRONG = "strong"


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
    max_position_weight_pct: float = Field(
        default=12.0,
        ge=3.0,
        le=50.0,
        description="종목당 총자산 대비 최대 비중 % (자동 매수)",
    )
    trade_hours_enabled: bool = Field(
        default=True,
        description="False면 24시간 자동 매수 허용",
    )
    trade_start_hour_kst: int = Field(default=8, ge=0, le=23)
    trade_end_hour_kst: int = Field(default=23, ge=1, le=24)
    paper_days_before_live_auto: int = Field(
        default=3,
        ge=0,
        le=30,
        description="실거래 자동투자 전 모의 자동투자 검증 일수",
    )
    stop_loss_pct: float = Field(default=5.0, ge=0.01, le=25.0)
    take_profit_pct: float = Field(default=5.0, ge=0.01, le=50.0)
    auto_exit_strength: AutoExitStrength = Field(
        default=AutoExitStrength.WEAK,
        description="자동투자 청산 강도: weak(약)~1%익절, medium(중)~3%, strong(강)~6%",
    )
    trading_fee_pct: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="편도 거래 수수료 % (모의·실거래 체결 반영)",
    )
    scan_interval_sec: int = Field(default=22, ge=10, le=300)
    min_buy_score: float = Field(default=28.0, ge=15.0, le=90.0)
    min_buy_krw: float = Field(
        default=6_000.0,
        ge=5_000.0,
        le=5_000_000.0,
        description="자동·승인 매수 건당 최소 금액(원). 업비트 하한 5,000원 이상",
    )
    min_entry_score: float = Field(default=38.0, ge=25.0, le=90.0)
    max_auto_buys_per_scan: int = Field(
        default=2,
        ge=0,
        le=8,
        description="자동투자 시 스캔당 최대 매수 건수",
    )
    paper_max_auto_buys_per_scan: int = Field(
        default=4,
        ge=0,
        le=10,
        description="모의 자동투자 스캔당 최대 매수",
    )
    paper_auto_deploy_pct: float = Field(
        default=40.0,
        ge=5.0,
        le=90.0,
        description="모의 자동투자 시 가용 현금 중 스캔당 배분 %",
    )
    daily_loss_limit_pct: float = Field(
        default=5.0,
        ge=1.0,
        le=25.0,
        description="당일 총자산 하락 % 초과 시 자동매수 중지",
    )
    allow_live_auto_invest: bool = Field(
        default=False,
        description="실거래 자동투자 허용(기본 끔)",
    )
    flash_guard_enabled: bool = Field(
        default=True,
        description="급락 감지·즉시 손절·종목 매수 일시 차단",
    )
    flash_drop_from_peak_pct: float = Field(
        default=4.5,
        ge=0.5,
        le=15.0,
        description="최근 고점 대비 % 하락 시 즉시 매도",
    )
    flash_tick_drop_pct: float = Field(
        default=2.0,
        ge=0.3,
        le=8.0,
        description="연속 시세 간 % 하락 (약 3초)",
    )
    flash_candle_1m_drop_pct: float = Field(
        default=5.5,
        ge=1.0,
        le=20.0,
        description="1분봉 최근 5봉 고점 대비 %",
    )
    flash_window_sec: float = Field(
        default=90.0,
        ge=30.0,
        le=600.0,
        description="단기 고점 계산 창(초)",
    )
    flash_block_minutes: float = Field(
        default=45.0,
        ge=5.0,
        le=240.0,
        description="급락 후 해당 종목 신규 매수 차단(분)",
    )
    flash_hard_stop_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=30.0,
        description="0이면 손절%×1.5 자동, 평단 대비 긴급 손절 %",
    )
    moonshot_enabled: bool = Field(
        default=True,
        description="24h 급등·고유동 종목을 급등(moonshot) 티어로 분류",
    )
    moonshot_min_change_24h_pct: float = Field(
        default=8.0,
        ge=4.0,
        le=40.0,
        description="급등 분류 최소 24h 상승 %",
    )
    moonshot_max_change_24h_pct: float = Field(
        default=60.0,
        ge=30.0,
        le=200.0,
        description="이미 과열 구간(추격 위험) 상한 %",
    )
    moonshot_min_volume_usdt: float = Field(
        default=1_200_000.0,
        ge=400_000.0,
        le=50_000_000.0,
        description="급등 분류 최소 24h 거래대금(USDT)",
    )
    moonshot_min_entry_score: float = Field(
        default=32.0,
        ge=18.0,
        le=70.0,
        description="차트 진입 미충족 시 급등 최소 진입점수",
    )
    moonshot_momentum_exit_enabled: bool = Field(
        default=True,
        description="급등주 24h 기세 기반 손익절 자동 (약·중·강 무관)",
    )
    moonshot_min_stop_loss_pct: float = Field(
        default=4.0,
        ge=3.0,
        le=12.0,
        description="급등 기세 손절 하한 %",
    )
    moonshot_max_stop_loss_pct: float = Field(
        default=8.0,
        ge=3.0,
        le=15.0,
        description="급등 기세 손절 상한 %",
    )
    moonshot_min_take_profit_pct: float = Field(
        default=5.0,
        ge=3.0,
        le=50.0,
        description="급등 기세 익절 하한 %",
    )
    moonshot_max_take_profit_pct: float = Field(
        default=12.0,
        ge=5.0,
        le=50.0,
        description="급등 기세 익절 상한 %",
    )
    moonshot_stop_loss_pct: float = Field(
        default=6.0,
        ge=3.0,
        le=15.0,
        description="기세 자동 끔 시 급등 고정 손절 %",
    )
    moonshot_take_profit_pct: float = Field(
        default=20.0,
        ge=3.0,
        le=50.0,
        description="기세 자동 끔 시 급등 고정 익절 %",
    )
    moonshot_flash_relax_factor: float = Field(
        default=2.0,
        ge=1.0,
        le=4.0,
        description="급등 보유 시 급락 감지 임계값 배율(클수록 완화)",
    )
    news_enabled: bool = Field(
        default=True,
        description="뉴스·기사 기반 급등 보조 신호 사용",
    )
    news_boost_min_score: float = Field(
        default=25.0,
        ge=10.0,
        le=80.0,
        description="뉴스급등 판정·moonshot 완화 최소 점수",
    )
    news_cache_ttl_sec: int = Field(
        default=420,
        ge=300,
        le=900,
        description="뉴스 피드 캐시 TTL(초)",
    )
    surge_auto_expire_enabled: bool = Field(
        default=True,
        description="뉴스·기사 기반 급등·하락 분류 자동 만료",
    )
    surge_tag_ttl_hours: float = Field(
        default=48.0,
        ge=1.0,
        le=168.0,
        description="급등주 뉴스 분류 유지 시간(시간)",
    )
    downtrend_tag_ttl_hours: float = Field(
        default=24.0,
        ge=1.0,
        le=168.0,
        description="하락주 뉴스 분류 유지 시간(시간)",
    )
    cryptopanic_api_key: str = Field(
        default="",
        description="CryptoPanic API 키 (선택, 없으면 RSS·CoinGecko만)",
    )
    news_llm_enabled: bool = Field(
        default=False,
        description="뉴스 AI 방향 판단 (API 키 필요, 기본 끔)",
    )
    news_llm_provider: str = Field(
        default="gemini",
        description="gemini | openai | auto (기본 Gemini)",
    )
    news_llm_api_key: str = Field(
        default="",
        description="뉴스 AI API 키 (Gemini, gemini_api_key와 동일)",
    )
    openai_api_key: str = Field(
        default="",
        description="OpenAI API 키 (뉴스 AI 대체, 선택)",
    )
    gemini_api_key: str = Field(
        default="",
        description="Google Gemini API 키 (뉴스 AI, 기본)",
    )
    news_llm_bearish_block_threshold: int = Field(
        default=60,
        ge=40,
        le=95,
        description="bearish 신뢰도 ≥ 이 값이면 뉴스급등·moonshot 보조 차단",
    )
    news_llm_max_articles_per_scan: int = Field(
        default=8,
        ge=1,
        le=20,
        description="스캔당 LLM 분석 기사 수 상한 (비용 제어)",
    )
    backtest_ai_enabled: bool = Field(
        default=False,
        description="백테스트 배치 후 Gemini로 SL/TP·종목 패턴 제안 (gemini_api_key 필요)",
    )
    backtest_ai_max_symbols_per_batch: int = Field(
        default=5,
        ge=1,
        le=12,
        description="배치당 Gemini 분석 종목 수 상한",
    )
    ai_auto_settings: bool = Field(
        default=True,
        description="True면 BT·학습이 손익절·스캔점수·자동배분을 조정",
    )
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
        "cryptopanic_api_key",
        "news_llm_api_key",
        "openai_api_key",
        "gemini_api_key",
        mode="before",
    )
    @classmethod
    def strip_secrets(cls, v):
        return (v or "").strip()

    @field_validator("stop_loss_pct", "take_profit_pct", mode="before")
    @classmethod
    def round_tp_sl_pct(cls, v):
        if v is None or v == "":
            return v
        return round(float(v), 2)

    @field_validator("auto_exit_strength", mode="before")
    @classmethod
    def coerce_auto_exit_strength(cls, v):
        if v is None or v == "":
            return AutoExitStrength.WEAK
        raw = str(v).strip().lower()
        aliases = {"약": "weak", "중": "medium", "강": "strong"}
        raw = aliases.get(raw, raw)
        try:
            return AutoExitStrength(raw)
        except ValueError:
            return AutoExitStrength.WEAK

    @model_validator(mode="after")
    def moonshot_sl_tp_bounds(self):
        if self.moonshot_max_stop_loss_pct < self.moonshot_min_stop_loss_pct:
            raise ValueError(
                "moonshot_max_stop_loss_pct must be >= moonshot_min_stop_loss_pct"
            )
        if self.moonshot_max_take_profit_pct < self.moonshot_min_take_profit_pct:
            raise ValueError(
                "moonshot_max_take_profit_pct must be >= moonshot_min_take_profit_pct"
            )
        return self

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
    auto_exit_sl_pct: float = 0.0
    auto_exit_tp_pct: float = 0.0
    exit_profile: str = Field(
        default="",
        description="moonshot | (빈값=일반 auto_exit_strength)",
    )
    excluded_from_auto: bool = False
    custom_sl_tp: bool = False
    custom_stop_loss_pct: float = 0.0
    custom_take_profit_pct: float = 0.0
    # 실거래: 업비트 API 기준 (잔고·평단·시세·평가)
    data_source: str = ""
    exchange_quantity: float = 0.0
    avg_buy_price_krw: float = 0.0
    current_price_krw: float = 0.0
    valuation_krw: float = 0.0

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
        if self.avg_buy_price_krw > 0 and self.current_price_krw > 0:
            return (
                (self.current_price_krw - self.avg_buy_price_krw)
                / self.avg_buy_price_krw
                * 100
            )
        if self.cost_basis_krw > 0 and self.current_value_krw > 0:
            return (
                (self.current_value_krw - self.cost_basis_krw)
                / self.cost_basis_krw
                * 100
            )
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
    data_source: str = "paper"
    upbit_synced_at: Optional[float] = None


class UpbitHoldingRow(BaseModel):
    symbol: str
    market: str
    currency: str
    quantity: float
    avg_buy_price_krw: float
    current_price_krw: float
    valuation_krw: float
    cost_basis_krw: float


class UpbitAccountSnapshot(BaseModel):
    """업비트 계정 API 기준 스냅샷 (실거래 표시·검증용)."""
    source: str = "upbit"
    synced_at: float
    krw_balance: float
    coin_valuation_krw: float
    total_assets_krw: float
    invested_principal_krw: float
    holdings: list[UpbitHoldingRow] = Field(default_factory=list)


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
    entry_scalp_ok: bool = False
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
    price_krw: float = 0.0
    quantity: float
    amount_krw: float
    amount_usdt: float
    reason: str
    is_auto: bool = True
    order_uuid: str = ""
    entry_mode: str = ""  # 롱 | 단타 | AI — 매매 내역 표시용
    exit_kind: str = ""  # tp | sl | manual | approval — 사유 재분류용


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
    price_usdt: float = 0.0
    quantity_est: float = 0.0
    stop_loss_price_usdt: float = 0.0
    take_profit_price_usdt: float = 0.0
    stop_loss_krw: float = 0.0
    take_profit_krw: float = 0.0
    stop_loss_pct: float = 0.0
    take_profit_pct: float = 0.0
    sl_tp_source: str = ""
    entry_tier: str = "watch"
    entry_detail: str = ""
    bt_line: str = Field(
        default="",
        description="BT 점수·학습 기준 한 줄 요약",
    )
    change_24h: float = 0.0
    volume_usdt: float = 0.0
    trend: str = ""
    news_score: float = 0.0
    news_surge: bool = False
    news_detail: str = ""
    news_url: str = ""
    selected: bool = True


class RecommendationApplyItem(BaseModel):
    symbol: str
    amount_krw: float = Field(ge=5_000, le=500_000_000)


class ApplyRecommendationsRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list, description="비우면 선택된 항목 전체")
    items: list[RecommendationApplyItem] = Field(
        default_factory=list,
        description="심볼별 매수 금액 (있으면 symbols보다 우선)",
    )


class DirectionSignalItem(BaseModel):
    signal_id: str
    symbol: str
    base: str
    name_ko: str = ""
    display: str = ""
    side: str  # long | short
    score: float = 0.0
    price_usdt: float = 0.0
    rsi: float = 0.0
    trend: str = ""
    outlook: str = ""
    detail: str = ""
    reasons: list[str] = Field(default_factory=list)
    scanned_at: float = 0.0


class BacktestLearningStatus(BaseModel):
    long_min_bt_score: float = 42.0
    scalp_min_bt_score: float = 38.0
    long_sl_pct: float = 0.0
    long_tp_pct: float = 0.0
    scalp_sl_pct: float = 0.0
    scalp_tp_pct: float = 0.0
    recent_batch_win_rate: float = 0.0
    adjust_cycles: int = 0
    blocked_count: int = 0
    last_adjust_message: str = ""
    execution_win_rate: float = 0.0
    execution_feedback_count: int = 0
    data_maturity_pct: float = 0.0


class AutoInvestRiskStatus(BaseModel):
    kill_switch: bool = False
    kill_reason: str = ""
    daily_pnl_krw: float = 0.0
    daily_pnl_pct: float = 0.0
    day_equity_start_krw: float = 0.0
    risk_mode: str = ""
    message: str = ""


class BacktestStatus(BaseModel):
    running: bool = False
    last_run: float = 0.0
    message: str = ""
    symbols_tested: int = 0
    win_rate_pct: float = 0.0
    avg_return_pct: float = 0.0
    trades_simulated: int = 0
    cycles: int = 0
    best_sl_pct: float = 0.0
    best_tp_pct: float = 0.0
    symbols_in_store: int = 0
    last_batch_updated: int = 0
    learning: BacktestLearningStatus = Field(default_factory=BacktestLearningStatus)


class ActivityEntry(BaseModel):
    ts: float = 0.0
    phase: str = ""
    level: str = "info"
    message: str = ""


class BotStartRequest(BaseModel):
    """분석만 vs 자동투자(롱·단타·혼합)."""

    auto_invest: bool = False
    auto_long: bool = False
    auto_scalp: bool = False


class SurgeSymbolRequest(BaseModel):
    symbol: str
    reason: str = ""


class BotState(BaseModel):
    status: BotStatus = BotStatus.STOPPED
    """현재 bot.* 스캔·제안·로그가 반영하는 계정 (paper | live)."""
    active_trade_mode: str = "paper"
    view_symbol: str = "BTCUSDT"
    last_scan: Optional[float] = None
    message: str = "대기 중"
    auto_invest_active: bool = False
    auto_invest_long: bool = False
    auto_invest_scalp: bool = False
    auto_invest_message: str = ""
    auto_risk: AutoInvestRiskStatus = Field(default_factory=AutoInvestRiskStatus)
    paper_auto_full: bool = False
    candidates: list[CoinCandidate] = Field(default_factory=list)
    liquid_symbols: list[str] = Field(
        default_factory=list,
        description="거래대금 상위 종목 (탭 표시용, 추천과 별개)",
    )
    recommendations: list[InvestmentRecommendation] = Field(default_factory=list)
    long_signals: list[DirectionSignalItem] = Field(default_factory=list)
    short_signals: list[DirectionSignalItem] = Field(default_factory=list)
    direction_scan_message: str = ""
    backtest: BacktestStatus = Field(default_factory=BacktestStatus)
    recent_trades: list[TradeEvent] = Field(default_factory=list)
    manual_mode: bool = True
    activity_log: list[ActivityEntry] = Field(default_factory=list)
    phase: str = "idle"
    phase_detail: str = ""
    seconds_until_scan: int = 0
    ai_settings_summary: str = ""
    auto_buy_paused: bool = False
    scan_health: str = "ok"
    scan_health_detail: str = ""
    auto_invest_rejects: list[str] = Field(default_factory=list)
    surge_candidates_count: int = 0
    surge_candidates: list[str] = Field(
        default_factory=list,
        description="최근 스캔 moonshot(급등·뉴스급등) tier 심볼",
    )
    surge_tags: dict[str, str] = Field(
        default_factory=dict,
        description="심볼별 surge|downtrend 태그 (UI 배지)",
    )


class ManualBuyRequest(BaseModel):
    symbol: str
    amount_krw: float = Field(ge=5_000, le=500_000_000)


class ManualSellRequest(BaseModel):
    symbol: str
    percent: float = Field(default=100.0, ge=1.0, le=100.0)
    from_auto_only: bool = False


class SellAllRequest(BaseModel):
    percent: float = Field(default=100.0, ge=1.0, le=100.0)


class PositionExcludeRequest(BaseModel):
    exclude: bool


class PositionExitPlanRequest(BaseModel):
    """손익절: custom_sl_tp=True면 평단 대비 % 또는 USDT 가격으로 전량 자동 매도."""

    custom_sl_tp: bool
    stop_loss_pct: Optional[float] = Field(default=None, ge=0.01, le=50.0)
    take_profit_pct: Optional[float] = Field(default=None, ge=0.01, le=100.0)
    stop_loss_usdt: Optional[float] = Field(default=None, ge=0)
    take_profit_usdt: Optional[float] = Field(default=None, ge=0)


class AccountLinkInfo(BaseModel):
    linked: bool = False
    mode: str = "paper"
    message: str = ""
    last_sync: Optional[float] = None
    total_assets_krw: Optional[float] = None
    cash_krw: Optional[float] = None
    exchange: str = ""


class TabQuote(BaseModel):
    price_usdt: float = 0.0
    price_krw: float = 0.0
    change_24h: float = 0.0
    volume_24h_krw: float = 0.0


class StatusResponse(BaseModel):
    bot: BotState
    portfolio: PortfolioSnapshot
    config: AppConfig
    view: CoinView
    tabs: list[str] = Field(default_factory=list)
    tab_quotes: dict[str, TabQuote] = Field(default_factory=dict)
    account_link: AccountLinkInfo = Field(default_factory=AccountLinkInfo)
    upbit_snapshot: Optional[UpbitAccountSnapshot] = None

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.engine.portfolio_store import store
from app.engine.trader import TradingEngine
from app.config import settings as app_settings
from app.market.binance import binance
from app.market.scanner import top_usdt_symbols
from app.models import (
    AccountLinkInfo,
    AppConfig,
    ApplyRecommendationsRequest,
    ManualBuyRequest,
    ManualSellRequest,
    PositionExcludeRequest,
    SellAllRequest,
    StatusResponse,
    TradeMode,
)
from app.storage.credentials import (
    apply_credentials_to_config,
    config_for_response,
    get_active_keys,
    has_api_keys,
    save_credentials,
)
from app.market.live_exchange import close_all, test_exchange_connection

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

engine = TradingEngine()
_ws_clients: set[WebSocket] = set()
_broadcast_task: asyncio.Task | None = None
_ticker_cache: tuple[float, dict] | None = None
_last_live_sync: float = 0


api = APIRouter(prefix="/api")


async def _get_tickers() -> dict:
    global _ticker_cache
    now = time.time()
    if _ticker_cache and now - _ticker_cache[0] < 5:
        return _ticker_cache[1]
    t = await binance.tickers_24h()
    _ticker_cache = (now, t)
    return t


async def _build_status() -> dict:
    global _last_live_sync
    engine.bind_portfolio()
    link = AccountLinkInfo(mode=engine.config.trade_mode.value)

    if engine.config.trade_mode == TradeMode.LIVE:
        if not has_api_keys(engine.config):
            link.linked = False
            link.message = "API 키를 설정하세요"
        else:
            try:
                if time.time() - _last_live_sync > 8:
                    engine._link_message = await store.sync_live(engine.config)
                    _last_live_sync = time.time()
                engine.bind_portfolio()
                link.linked = True
                link.message = engine._link_message or "거래소 연동됨"
                link.last_sync = _last_live_sync
                link.exchange = engine.config.exchange or "upbit"
            except Exception as e:
                link.linked = False
                link.message = f"연동 실패: {e}"
    else:
        link.linked = True
        link.message = "모의투자 (시뮬 데이터 · 거래소 미연동)"

    portfolio = engine.portfolio
    prices = await engine.prices_map()
    tickers = await _get_tickers()
    snap = portfolio.snapshot(prices, engine.config)
    if link.linked and engine.config.trade_mode == TradeMode.LIVE:
        link.total_assets_krw = round(snap.total_value_krw, 0)
        link.cash_krw = round(snap.cash_krw, 0)
    if len(engine.bot.liquid_symbols) < 80:
        try:
            engine.bot.liquid_symbols = await top_usdt_symbols(
                app_settings.tab_symbol_limit
            )
        except Exception:
            pass
    view = engine.build_coin_view(engine.bot.view_symbol, prices, tickers)
    engine.bot.manual_mode = True
    engine.bot.recent_trades = portfolio.trades[-40:]
    tab_quotes = await engine.tab_quotes_map()

    payload = StatusResponse(
        bot=engine.bot,
        portfolio=snap,
        config=engine.config,
        view=view,
        tabs=engine.tab_symbols(),
        tab_quotes=tab_quotes,
        account_link=link,
    ).model_dump()
    payload["config"] = config_for_response(engine.config)
    payload["status_version"] = engine._status_version
    payload["all_trades"] = [t.model_dump() for t in portfolio.trades[-50:]]
    return payload


async def _broadcast_loop() -> None:
    while True:
        if _ws_clients:
            try:
                payload = await _build_status()
                dead: list[WebSocket] = []
                for ws in _ws_clients:
                    try:
                        await ws.send_json(payload)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    _ws_clients.discard(ws)
            except Exception:
                pass
        await asyncio.sleep(3 if engine.config.trade_mode == TradeMode.LIVE else 2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _broadcast_task
    engine.config = apply_credentials_to_config(engine.config)
    engine.bind_portfolio()
    engine.ensure_auto_guard()
    _broadcast_task = asyncio.create_task(_broadcast_loop())
    yield
    if _broadcast_task:
        _broadcast_task.cancel()
    if engine._guard_task:
        engine._guard_task.cancel()
    await engine.stop()
    store.persist_active(engine.config.trade_mode)
    await binance.close()
    await close_all()


app = FastAPI(title="AIDI Auto Invest", version="1.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@api.get("/status")
async def get_status():
    return await _build_status()


@api.post("/config")
async def set_config(cfg: AppConfig):
    ak, sk = get_active_keys(cfg)
    if ak or sk:
        save_credentials(cfg.exchange or "upbit", ak, sk, merge=True)
    merged = apply_credentials_to_config(cfg)
    msg = await engine.update_config(merged)
    engine.config = apply_credentials_to_config(engine.config)
    status = await _build_status()
    status["switch_message"] = msg
    return status


@api.post("/credentials/test")
async def credentials_test(cfg: AppConfig):
    """저장된 키 또는 요청 본문의 키로 거래소 연결 테스트."""
    draft = cfg.model_copy()
    ak, sk = get_active_keys(draft)
    if not ak or not sk:
        draft = apply_credentials_to_config(draft)
    else:
        draft.api_access_key = ak
        draft.api_secret_key = sk
    if not has_api_keys(draft):
        return {"ok": False, "message": "Access Key와 Secret Key를 입력하세요"}
    try:
        result = await test_exchange_connection(draft)
        return result
    except Exception as e:
        return {"ok": False, "message": str(e)}


@api.post("/bot/start")
async def bot_start():
    ok, msg = await engine.start()
    status = await _build_status()
    status["ok"] = ok
    status["message"] = msg
    return status


@api.post("/bot/stop")
async def bot_stop():
    await engine.stop()
    engine._persist()
    status = await _build_status()
    status["ok"] = True
    return status


@api.post("/recommendations/apply")
async def apply_recommendations(body: ApplyRecommendationsRequest):
    ok, msg = await engine.apply_recommendations(body.symbols, body.items)
    status = await _build_status()
    status["ok"] = ok
    status["message"] = msg
    return status


@api.post("/account/sync")
async def force_sync():
    """실거래 계정 강제 동기화."""
    if engine.config.trade_mode != TradeMode.LIVE:
        return {"ok": False, "message": "실거래 모드에서만 가능"}
    msg = await store.sync_live(engine.config)
    engine.bind_portfolio()
    status = await _build_status()
    status["ok"] = True
    status["message"] = msg
    return status


_CHART_INTERVALS = frozenset({"1s", "1m", "15m", "1h", "4h", "1d"})


@api.get("/chart/{symbol}")
async def chart(symbol: str, interval: str = "1h"):
    engine.bind_portfolio()
    sym = symbol.upper()
    iv = interval.lower() if interval.lower() in _CHART_INTERVALS else "1h"
    data = await engine.get_candles(sym, iv)
    markers = [m.model_dump() for m in engine.portfolio.chart_markers(sym)]
    return {
        "symbol": sym,
        "interval": iv,
        "candles": data,
        "markers": markers,
    }


@api.post("/position/{symbol}/exclude")
async def position_exclude(symbol: str, body: PositionExcludeRequest):
    ok, msg = await engine.set_position_exclude(symbol, body.exclude)
    status = await _build_status()
    status["ok"] = ok
    status["message"] = msg
    return status


@api.post("/view/{symbol}")
async def set_view(symbol: str):
    sym = symbol.upper()
    engine.set_view_symbol(sym)
    await engine.ensure_candidate_entry(sym)
    return await _build_status()


@api.post("/trade/buy")
async def trade_buy(req: ManualBuyRequest):
    ok, msg = await engine.manual_buy(req)
    status = await _build_status()
    status["ok"] = ok
    status["message"] = msg
    return status


@api.post("/trade/sell")
async def trade_sell(req: ManualSellRequest):
    ok, msg = await engine.manual_sell(req)
    status = await _build_status()
    status["ok"] = ok
    status["message"] = msg
    return status


@api.post("/trade/sell-all")
async def trade_sell_all(req: SellAllRequest):
    ok, msg = await engine.manual_sell_all(req.percent)
    status = await _build_status()
    status["ok"] = ok
    status["message"] = msg
    return status


@api.post("/chart/select/{symbol}")
async def legacy_select(symbol: str):
    engine.set_view_symbol(symbol.upper())
    return await _build_status()


async def _ws_handler(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    try:
        await ws.send_json(await _build_status())
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)


@api.websocket("/ws")
async def websocket_api(ws: WebSocket):
    await _ws_handler(ws)


app.include_router(api)


@app.websocket("/ws")
async def websocket_root(ws: WebSocket):
    await _ws_handler(ws)


if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/")
    async def index():
        return FileResponse(
            STATIC_DIR / "index.html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        if full_path.startswith("api"):
            return JSONResponse({"error": "not found"}, status_code=404)
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(
            STATIC_DIR / "index.html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

else:

    @app.get("/")
    async def root():
        return {"name": "AIDI", "build": "cd frontend && npm run build"}

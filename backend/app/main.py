import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.engine.portfolio import PortfolioManager
from app.engine.trader import TradingEngine
from app.market.binance import binance
from app.models import AppConfig, ManualBuyRequest, ManualSellRequest, StatusResponse

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

portfolio = PortfolioManager()
engine = TradingEngine(portfolio)
_ws_clients: set[WebSocket] = set()
_broadcast_task: asyncio.Task | None = None
_ticker_cache: tuple[float, dict] | None = None

api = APIRouter(prefix="/api")


async def _get_tickers() -> dict:
    global _ticker_cache
    import time

    now = time.time()
    if _ticker_cache and now - _ticker_cache[0] < 5:
        return _ticker_cache[1]
    t = await binance.tickers_24h()
    _ticker_cache = (now, t)
    return t


async def _build_status() -> dict:
    prices = await engine.prices_map()
    tickers = await _get_tickers()
    snap = portfolio.snapshot(prices, engine.config)
    view = engine.build_coin_view(engine.bot.view_symbol, prices, tickers)
    engine.bot.manual_mode = engine.can_manual_trade()
    engine.bot.recent_trades = portfolio.trades[-40:]
    payload = StatusResponse(
        bot=engine.bot,
        portfolio=snap,
        config=engine.config,
        view=view,
        tabs=engine.tab_symbols(),
    ).model_dump()
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
        await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _broadcast_task
    _broadcast_task = asyncio.create_task(_broadcast_loop())
    yield
    if _broadcast_task:
        _broadcast_task.cancel()
    await engine.stop()
    await binance.close()


app = FastAPI(title="AIDI Auto Invest", version="1.2.0", lifespan=lifespan)
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
    engine.update_config(cfg)
    return await _build_status()


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
    status = await _build_status()
    status["ok"] = True
    return status


@api.get("/chart/{symbol}")
async def chart(symbol: str, interval: str = "1h"):
    data = await engine.get_candles(symbol.upper(), interval)
    return {"symbol": symbol.upper(), "interval": interval, "candles": data}


@api.post("/view/{symbol}")
async def set_view(symbol: str):
    engine.set_view_symbol(symbol.upper())
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


# 하위 호환
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

# WebSocket 하위 호환 (/ws)
@app.websocket("/ws")
async def websocket_root(ws: WebSocket):
    await _ws_handler(ws)


@app.get("/api/ws")
async def ws_hint():
    return JSONResponse({"use": "WebSocket at /api/ws"})


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

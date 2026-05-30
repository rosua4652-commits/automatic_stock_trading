import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.engine.portfolio import PortfolioManager
from app.engine.trader import TradingEngine
from app.market.binance import binance
from app.models import AppConfig, StatusResponse

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

portfolio = PortfolioManager()
engine = TradingEngine(portfolio)
_ws_clients: set[WebSocket] = set()
_broadcast_task: asyncio.Task | None = None
_ticker_cache: tuple[float, dict] | None = None


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
    payload = StatusResponse(
        bot=engine.bot,
        portfolio=snap,
        config=engine.config,
        view=view,
    ).model_dump()
    payload["tabs"] = engine.tab_symbols()
    return payload


async def _broadcast_loop() -> None:
    while True:
        if _ws_clients:
            try:
                payload = await _build_status()
            except Exception:
                payload = None
            if payload:
                dead: list[WebSocket] = []
                for ws in _ws_clients:
                    try:
                        await ws.send_json(payload)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    _ws_clients.discard(ws)
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


app = FastAPI(title="AIDI Auto Invest", version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/status")
async def get_status():
    return await _build_status()


@app.post("/api/config")
async def set_config(cfg: AppConfig):
    engine.update_config(cfg)
    return await _build_status()


@app.post("/api/bot/start")
async def bot_start():
    await engine.start()
    return await _build_status()


@app.post("/api/bot/stop")
async def bot_stop():
    await engine.stop()
    return await _build_status()


@app.get("/api/chart/{symbol}")
async def chart(symbol: str, interval: str = "1h"):
    return await engine.get_candles(symbol.upper(), interval)


@app.post("/api/view/{symbol}")
async def set_view(symbol: str):
    sym = engine.set_view_symbol(symbol.upper())
    return await _build_status()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
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


if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        if full_path.startswith("api") or full_path.startswith("ws"):
            return {"error": "not found"}
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")

else:

    @app.get("/")
    async def root():
        return {"name": "AIDI Auto Invest API", "build_frontend": True}

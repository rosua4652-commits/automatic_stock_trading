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
from app.models import AppConfig, BotStatus, StatusResponse

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

portfolio = PortfolioManager()
engine = TradingEngine(portfolio)
_ws_clients: set[WebSocket] = set()
_broadcast_task: asyncio.Task | None = None


async def _broadcast_loop() -> None:
    while True:
        if _ws_clients:
            payload = await _build_status()
            dead: list[WebSocket] = []
            for ws in _ws_clients:
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                _ws_clients.discard(ws)
        await asyncio.sleep(2)


async def _build_status() -> dict:
    prices = await engine.prices_map()
    snap = portfolio.snapshot(prices, engine.config)
    return StatusResponse(bot=engine.bot, portfolio=snap, config=engine.config).model_dump()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _broadcast_task
    engine.subscribe(lambda: None)
    _broadcast_task = asyncio.create_task(_broadcast_loop())
    yield
    if _broadcast_task:
        _broadcast_task.cancel()
    await engine.stop()
    await binance.close()


app = FastAPI(title="AIDI Auto Invest", version="1.0.0", lifespan=lifespan)
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
    return {"ok": True}


@app.post("/api/bot/start")
async def bot_start():
    await engine.start()
    return {"status": engine.bot.status}


@app.post("/api/bot/stop")
async def bot_stop():
    await engine.stop()
    return {"status": engine.bot.status}


@app.get("/api/chart/{symbol}")
async def chart(symbol: str, interval: str = "1h"):
    return await engine.get_candles(symbol.upper(), interval)


@app.post("/api/chart/select/{symbol}")
async def select_symbol(symbol: str):
    engine.bot.selected_symbol = symbol.upper()
    return {"symbol": engine.bot.selected_symbol}


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
        index = STATIC_DIR / "index.html"
        if full_path.startswith("api") or full_path.startswith("ws"):
            return {"error": "not found"}
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(index)

else:

    @app.get("/")
    async def root():
        return {
            "name": "AIDI Auto Invest API",
            "hint": "프론트엔드를 빌드하면 UI가 제공됩니다. cd frontend && npm run build",
        }

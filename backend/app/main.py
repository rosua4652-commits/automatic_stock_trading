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
from app.market.upbit_data import market
from app.market.scanner import top_usdt_symbols
from app.models import (
    UpbitAccountSnapshot,
    AccountLinkInfo,
    AppConfig,
    ApplyRecommendationsRequest,
    BotStartRequest,
    ManualBuyRequest,
    ManualSellRequest,
    PositionExcludeRequest,
    PositionExitPlanRequest,
    SellAllRequest,
    StatusResponse,
    TradeMode,
)
from app.storage.credentials import (
    apply_credentials_to_config,
    config_for_response,
    get_active_keys,
    get_keys_from_body,
    has_api_keys,
    save_credentials,
)
from app.market.live_exchange import close_all, test_exchange_connection
from app.market.ipv4_http import outbound_ipv4_via_same_stack, upbit_resolved_ipv4
from app.market.network_info import get_outbound_public_ip
from app.storage.credentials import load_credentials, mask_key
from app.aidi_log import get_aidi_logger, setup_aidi_logging
from app.aidi_middleware import AidiActionLogMiddleware

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# PC에서 run.bat 시작 시 표시 — GitHub 최신과 비교용
AIDI_BUILD = "2026-05-31-paper-full-auto"


def _load_pc_path_hint() -> str:
    hint_file = REPO_ROOT / "pc-path.txt"
    if not hint_file.is_file():
        return ""
    try:
        for line in hint_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    except OSError:
        pass
    return ""


PC_PATH_HINT = _load_pc_path_hint()

engine = TradingEngine()
_ws_clients: set[WebSocket] = set()
_broadcast_task: asyncio.Task | None = None
_ticker_cache: tuple[float, dict] | None = None
_last_live_sync: float = 0


api = APIRouter(prefix="/api")


async def _get_tickers() -> dict:
    global _ticker_cache
    now = time.time()
    if _ticker_cache and now - _ticker_cache[0] < 20:
        return _ticker_cache[1]
    try:
        t = await market.tickers_24h()
        _ticker_cache = (now, t)
        return t
    except Exception:
        if _ticker_cache:
            return _ticker_cache[1]
        return {}


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
    upbit_snap: UpbitAccountSnapshot | None = None
    upbit_synced_at: float | None = None
    if engine.config.trade_mode == TradeMode.LIVE and link.linked:
        raw = store._live_meta.get("upbit_snapshot")
        if raw:
            try:
                upbit_snap = UpbitAccountSnapshot(**raw)
                upbit_synced_at = upbit_snap.synced_at
            except Exception:
                upbit_snap = None
        snap = portfolio.snapshot(
            prices,
            engine.config,
            upbit_truth=True,
            upbit_synced_at=upbit_synced_at,
        )
    else:
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
    engine.bot.manual_mode = not engine.bot.auto_invest_active
    if engine.bot.auto_invest_active or engine.config.trade_mode == TradeMode.PAPER:
        engine._refresh_auto_risk_status()
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
        upbit_snapshot=upbit_snap,
    ).model_dump()
    payload["config"] = config_for_response(engine.config)
    payload["status_version"] = engine._status_version
    payload["aidi_build"] = AIDI_BUILD
    payload["aidi_capabilities"] = {
        "exit_plan_pct": True,
        "manual_sl_tp": True,
        "small_sell_retry": True,
        "trade_history_merge": True,
        "upbit_trade_history": True,
        "auto_invest_long_scalp": True,
        "backtest_learning": True,
        "paper_full_auto": True,
        "daily_loss_kill": True,
        "execution_feedback": True,
    }
    payload["all_trades"] = [t.model_dump() for t in portfolio.trades[-500:]]
    if engine.config.trade_mode == TradeMode.LIVE:
        err = store._live_meta.get("trades_sync_error")
        if err:
            payload["trades_sync_error"] = str(err)
        payload["trades_display_count"] = int(
            store._live_meta.get("trades_display_count") or len(portfolio.trades)
        )
        payload["trades_orders_fetched"] = int(
            store._live_meta.get("trades_orders_fetched") or 0
        )
    outbound = await get_outbound_public_ip()
    ip4 = await outbound_ipv4_via_same_stack()
    cred = load_credentials()
    ak = cred.get("api_access_key") or engine.config.api_access_key or ""
    register_ip = ip4 or outbound or ""
    payload["network"] = {
        "outbound_ip": outbound or "",
        "outbound_ipv4_stack": ip4 or "",
        "register_on_upbit": register_ip,
        "saved_access_key": mask_key(ak, 4) if ak else "",
        "api_routes": {
            "outbound_ip": "/api/network/outbound-ip",
            "diagnose": "/api/network/diagnose",
        },
    }
    if (
        not link.linked
        and engine.config.trade_mode == TradeMode.LIVE
        and register_ip
        and ("허용 IP" in (link.message or "") or "no_authorization_ip" in (link.message or ""))
    ):
        key_hint = mask_key(ak, 4) if ak else "????"
        link.message = (
            f"{link.message} "
            f"(AIDI 나가는 IP: {register_ip} — 업비트 Open API 키 [{key_hint}] 허용 IP에 등록)"
        )
        payload["account_link"] = link.model_dump()
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


setup_aidi_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _broadcast_task
    get_aidi_logger().info("AIDI 서버 시작 · 빌드 %s", AIDI_BUILD)
    engine.config = apply_credentials_to_config(engine.config)
    engine.bind_portfolio()
    engine.ensure_auto_guard()
    from app.engine.backtest_runner import ensure_backtest_loop, stop_backtest_loop

    from app.engine.backtest_runner import get_accumulator

    engine._backtest_acc = get_accumulator()
    ensure_backtest_loop(engine)
    _broadcast_task = asyncio.create_task(_broadcast_loop())
    yield
    if _broadcast_task:
        _broadcast_task.cancel()
    stop_backtest_loop()
    if engine._guard_task:
        engine._guard_task.cancel()
    await engine.stop()
    store.persist_active(engine.config.trade_mode)
    await market.close()
    await close_all()


app = FastAPI(title="AIDI Auto Invest", version="1.3.1", lifespan=lifespan)
app.add_middleware(AidiActionLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@api.get("/version")
async def api_version():
    return {
        "build": AIDI_BUILD,
        "app": app.version,
        "ok": True,
        "pc_path_hint": PC_PATH_HINT,
        "features": {
            "network_routes": True,
            "upbit_probe": True,
            "status_network_field": True,
            "upbit_hs512": True,
        },
    }


@api.get("/status")
async def get_status():
    return await _build_status()


@api.post("/config")
async def set_config(cfg: AppConfig):
    cfg.exchange = "upbit"
    body_ak, body_sk = get_keys_from_body(cfg)
    ex = "upbit"
    if body_ak and body_sk:
        save_credentials(ex, body_ak, body_sk, merge=False)
    elif body_ak or body_sk:
        return JSONResponse(
            {
                "error": "incomplete_keys",
                "message": "Access Key와 Secret Key를 둘 다 입력한 뒤 저장하세요.",
            },
            status_code=400,
        )
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
    saved = apply_credentials_to_config(draft)
    ak_d, sk_d = get_active_keys(draft)
    ak_s, sk_s = get_active_keys(saved)

    if ak_d or sk_d:
        if not (ak_d and sk_d):
            return {
                "ok": False,
                "message": "Access Key와 Secret Key를 둘 다 입력하세요. (새 키 발급 시 두 값 모두 붙여넣기 → 저장)",
            }
        ak, sk = ak_d, sk_d
        key_source = "입력한 키"
    elif ak_s and sk_s:
        ak, sk = ak_s, sk_s
        key_source = "PC에 저장된 키"
    else:
        return {"ok": False, "message": "Access Key와 Secret Key를 입력하세요"}

    draft.api_access_key = ak
    draft.api_secret_key = sk
    draft.exchange = cfg.exchange or draft.exchange or "upbit"
    outbound = await outbound_ipv4_via_same_stack() or await get_outbound_public_ip()
    key_hint = mask_key(ak, 4)
    if (draft.exchange or "upbit").lower() == "upbit":
        from app.market.upbit_client import upbit_client

        upbit_client.configure(ak, sk)
        probe = await upbit_client.probe_accounts()
        probe["key_source"] = key_source
        probe["access_key_hint"] = key_hint
        if probe.get("ok"):
            probe["message"] = (
                f"연결 성공 · 계정 {probe.get('accounts', 0)}개 · IP {outbound or probe.get('outbound_ipv4_stack', '')}"
            )
            return probe
        probe["ok"] = False
        probe["message"] = (
            f"업비트 거부 [{probe.get('upbit_error_name') or 'error'}]: "
            f"{probe.get('upbit_error_message') or probe.get('raw_body', '')}"
        )
        if outbound:
            probe["outbound_ip"] = outbound
        if probe.get("upbit_error_name") == "no_authorization_ip":
            probe["hint"] = (
                f"Open API 키 [{key_hint}] 행에 IP [{outbound}] 등록 여부 확인. "
                f"다른 키에만 IP 등록했거나 Access/Secret 짝이 다르면 동일 오류가 납니다."
            )
        return probe
    try:
        result = await test_exchange_connection(draft)
        if outbound:
            result["outbound_ip"] = outbound
        result["access_key_hint"] = key_hint
        result["key_source"] = key_source
        return result
    except Exception as e:
        body: dict = {
            "ok": False,
            "message": str(e),
            "access_key_hint": key_hint,
            "key_source": key_source,
        }
        if outbound:
            body["outbound_ip"] = outbound
        return body


@api.get("/network/outbound-ip")
async def outbound_ip():
    ip = await get_outbound_public_ip()
    ip4 = await outbound_ipv4_via_same_stack()
    return {
        "outbound_ip": ip or "",
        "outbound_ipv4_stack": ip4 or "",
        "upbit_ipv4_targets": upbit_resolved_ipv4(),
    }


@api.get("/network/diagnose")
async def network_diagnose():
    cred = load_credentials()
    ak = cred.get("api_access_key") or ""
    sk = cred.get("api_secret_key") or ""
    ip4 = await outbound_ipv4_via_same_stack()
    out: dict = {
        "outbound_ip": await get_outbound_public_ip(),
        "outbound_ipv4_stack": ip4,
        "upbit_ipv4_targets": upbit_resolved_ipv4(),
        "saved_access_key": mask_key(ak, 4) if ak else "",
        "has_saved_secret": bool(sk),
        "steps": [
            "1. outbound_ipv4_stack 를 업비트 Open API 허용 IP에 등록",
            "2. AIDI 설정에 새 Access·Secret 둘 다 입력 후 [저장]",
            "3. 연결 테스트 — upbit_error_name 이 비어 있으면 성공",
        ],
    }
    if ak and sk:
        from app.market.upbit_client import upbit_client

        upbit_client.configure(ak, sk)
        out["upbit_probe"] = await upbit_client.probe_accounts()
    else:
        out["upbit_probe"] = {"ok": False, "message": "저장된 API 키 없음"}
    return out


@api.post("/bot/start")
async def bot_start(body: BotStartRequest | None = None):
    req = body or BotStartRequest()
    if req.auto_invest and not (req.auto_long or req.auto_scalp):
        return JSONResponse(
            {
                "ok": False,
                "message": "자동투자: 롱 또는 단타를 하나 이상 선택하세요",
            },
            status_code=400,
        )
    ok, msg = await engine.start(
        auto_invest=req.auto_invest,
        auto_long=req.auto_long,
        auto_scalp=req.auto_scalp,
    )
    status = await _build_status()
    status["ok"] = ok
    status["message"] = msg
    return status


@api.post("/risk/reset-kill")
async def risk_reset_kill():
    """일손실 킬 스위치 수동 해제 (당일)."""
    from app.engine.risk_manager import reset_kill_switch

    msg = reset_kill_switch()
    engine._refresh_auto_risk_status()
    status = await _build_status()
    status["ok"] = True
    status["message"] = msg
    return status


@api.post("/bot/stop")
async def bot_stop():
    await engine.stop()
    engine._persist()
    status = await _build_status()
    status["ok"] = True
    return status


@api.post("/signals/scan/{side}")
async def scan_direction_signals(side: str):
    """side: long | short — 버튼으로 롱/숏 분석."""
    ok, msg = await engine.scan_direction_signals(side)
    status = await _build_status()
    status["ok"] = ok
    status["message"] = msg
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
    store._live_meta["trades_force_sync"] = True
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
    from app.market.upbit_data import market as upbit_market

    stale = False
    chart_error = ""
    try:
        data = await engine.get_candles(sym, iv)
        if not data:
            cached = upbit_market.get_cached_klines(sym, iv)
            if cached:
                stale = True
                chart_error = "업비트 요청 제한 — 캐시 차트 표시"
                data = [
                    {
                        "time": int(r[0] // 1000),
                        "open": float(r[1]),
                        "high": float(r[2]),
                        "low": float(r[3]),
                        "close": float(r[4]),
                        "volume": float(r[5]),
                    }
                    for r in cached
                ]
    except Exception as e:
        chart_error = str(e)[:120]
        cached = upbit_market.get_cached_klines(sym, iv) or []
        stale = True
        data = [
            {
                "time": int(r[0] // 1000),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),
            }
            for r in cached
        ]
    markers = [m.model_dump() for m in engine.portfolio.chart_markers(sym)]
    return {
        "symbol": sym,
        "interval": iv,
        "candles": data,
        "markers": markers,
        "stale": stale,
        "chart_error": chart_error,
    }


@api.post("/position/{symbol}/exit-plan")
async def position_exit_plan(symbol: str, body: PositionExitPlanRequest):
    ok, msg = await engine.set_position_exit_plan(
        symbol,
        custom_sl_tp=body.custom_sl_tp,
        stop_loss_pct=body.stop_loss_pct,
        take_profit_pct=body.take_profit_pct,
        stop_loss_usdt=body.stop_loss_usdt,
        take_profit_usdt=body.take_profit_usdt,
    )
    status = await _build_status()
    status["ok"] = ok
    status["message"] = msg
    return status


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


_ws_logged_once = False


async def _ws_handler(ws: WebSocket):
    global _ws_logged_once
    await ws.accept()
    _ws_clients.add(ws)
    if not _ws_logged_once:
        _ws_logged_once = True
        get_aidi_logger().info(
            "브라우저 WebSocket 연결 · 실시간 상태 %d초 간격",
            3 if engine.config.trade_mode == TradeMode.LIVE else 2,
        )
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
        if full_path.startswith("api/") or full_path == "api":
            return JSONResponse(
                {
                    "error": "api_not_found",
                    "detail": "API 경로 없음. run.bat 종료 후 최신 코드로 다시 실행하세요.",
                    "try": "/api/status 또는 /api/network/diagnose",
                },
                status_code=404,
            )
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

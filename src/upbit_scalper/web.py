from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .ai_client import AIAnalysisClient
from .config import AppConfig
from .reporting import build_portfolio_report
from .runner import BotController, TradingBot
from .runtime_settings import RuntimeSettingsStore
from .storage import read_jsonl
from .upbit import UpbitClient


def serve(host: str = "0.0.0.0", port: int = 8080, interval_seconds: int = 60) -> None:
    settings_store = RuntimeSettingsStore()

    def build_runtime() -> dict[str, Any]:
        config = settings_store.apply(AppConfig.from_env())
        bot = TradingBot(config, UpbitClient(config.credentials))
        ai_client = AIAnalysisClient(config)
        interval = int(settings_store.load().get("bot_interval_seconds", interval_seconds))
        return {"config": config, "bot": bot, "ai_client": ai_client, "interval": interval}

    runtime = build_runtime()
    controller = BotController(runtime["bot"], interval_seconds=runtime["interval"])

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_html(_dashboard_html())
            elif parsed.path == "/api/status":
                self._send_json({"ok": True, "status": controller.status()})
            elif parsed.path == "/api/settings":
                self._send_json(
                    {
                        "ok": True,
                        "settings": settings_store.public_settings(runtime["config"], controller.interval_seconds),
                        "saved_overrides": settings_store.load(),
                    }
                )
            elif parsed.path == "/api/logs":
                limit = int(parse_qs(parsed.query).get("limit", ["30"])[0])
                self._send_json({"ok": True, "events": read_jsonl("logs/bot_events.jsonl")[-limit:]})
            elif parsed.path == "/api/report":
                report_path = build_portfolio_report()
                self._send_json({"ok": True, "report": str(report_path)})
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/start":
                body = self._read_body()
                mode = body.get("mode") or runtime["config"].trading_mode
                started = controller.start(mode)
                self._send_json({"ok": True, "started": started, "status": controller.status()})
            elif parsed.path == "/api/stop":
                controller.stop()
                self._send_json({"ok": True, "status": controller.status()})
            elif parsed.path == "/api/settings":
                saved = settings_store.save(self._read_body())
                new_runtime = build_runtime()
                runtime.update(new_runtime)
                controller.configure(runtime["bot"], runtime["interval"])
                self._send_json(
                    {
                        "ok": True,
                        "settings": settings_store.public_settings(runtime["config"], controller.interval_seconds),
                        "saved_overrides": saved,
                        "status": controller.status(),
                    }
                )
            elif parsed.path == "/api/step":
                event = runtime["bot"].step(runtime["config"].trading_mode)
                self._send_json({"ok": True, "event": event})
            elif parsed.path == "/api/scan":
                signals = runtime["bot"].rank_signals()[:10]
                self._send_json({"ok": True, "signals": signals})
            elif parsed.path == "/api/ai":
                signals = runtime["bot"].rank_signals()[:1]
                analysis = runtime["ai_client"].summarize_signal(signals[0], {"source": "web"}) if signals else "신호가 없습니다."
                self._send_json({"ok": True, "analysis": analysis})
            elif parsed.path == "/api/portfolio":
                snapshot = runtime["bot"].portfolio_snapshot()
                self._send_json({"ok": True, "snapshot": snapshot})
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length == 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}

        def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(_jsonable(payload), ensure_ascii=False, indent=2).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, html: str) -> None:
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Dashboard running on http://{host}:{port}")
    server.serve_forever()


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _dashboard_html() -> str:
    return """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI 업비트 단타 봇</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 0; background: #0f172a; color: #e2e8f0; }
    header { padding: 20px 28px; background: #111827; border-bottom: 1px solid #334155; }
    main { padding: 24px; display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 18px; }
    section { background: #111827; border: 1px solid #334155; border-radius: 12px; padding: 18px; }
    button { margin: 4px; padding: 10px 14px; border: 0; border-radius: 8px; background: #2563eb; color: white; cursor: pointer; }
    button.danger { background: #dc2626; }
    button.safe { background: #16a34a; }
    label { display: block; margin: 10px 0 4px; color: #cbd5e1; font-size: 14px; }
    input, select { width: 100%; box-sizing: border-box; padding: 9px; border-radius: 8px; border: 1px solid #475569; background: #020617; color: #e2e8f0; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
    pre { overflow: auto; white-space: pre-wrap; background: #020617; padding: 12px; border-radius: 8px; max-height: 420px; }
    .muted { color: #94a3b8; }
  </style>
</head>
<body>
  <header>
    <h1>AI 업비트 단타 봇 대시보드</h1>
    <p class="muted">기본은 모의투자 모드입니다. 실거래는 환경변수에서 별도로 활성화해야 합니다.</p>
  </header>
  <main>
    <section>
      <h2>봇 제어</h2>
      <button class="safe" onclick="post('/api/start', {mode:'paper'})">모의투자 지속 실행</button>
      <button class="safe" onclick="startConfigured()">현재 설정으로 지속 실행</button>
      <button onclick="post('/api/step', {})">1회 분석/실행</button>
      <button class="danger" onclick="post('/api/stop', {})">중단</button>
      <button onclick="loadStatus()">상태 새로고침</button>
      <pre id="status">불러오는 중...</pre>
    </section>
    <section>
      <h2>운용 설정</h2>
      <p class="muted">API 키는 화면에 표시하지 않습니다. 실거래는 .env의 LIVE_TRADING_ENABLED=true가 켜져 있어야 가능합니다.</p>
      <div class="grid">
        <div><label>AI 분석</label><select id="ai_enabled"><option value="true">활성</option><option value="false">비활성</option></select></div>
        <div><label>거래 모드</label><select id="trading_mode"><option value="paper">모의투자</option><option value="live">실거래</option></select></div>
        <div><label>AI 모델</label><input id="ai_model"></div>
        <div><label>반복 주기(초)</label><input id="bot_interval_seconds" type="number" min="5"></div>
        <div><label>총 운용 예산(KRW)</label><input id="total_budget_krw" type="number" min="0"></div>
        <div><label>1회 최대 진입금(KRW)</label><input id="max_position_krw" type="number" min="0"></div>
        <div><label>1회 최소 진입금(KRW)</label><input id="min_position_krw" type="number" min="0"></div>
        <div><label>동시 보유 수</label><input id="max_open_positions" type="number" min="1"></div>
        <div><label>일일 손실 한도(KRW)</label><input id="daily_loss_limit_krw" type="number" min="0"></div>
        <div><label>연속 손절 중단 횟수</label><input id="stop_after_consecutive_losses" type="number" min="1"></div>
        <div><label>익절(%)</label><input id="take_profit_pct" type="number" step="0.1"></div>
        <div><label>손절(%)</label><input id="stop_loss_pct" type="number" step="0.1"></div>
        <div><label>트레일링 스탑(%)</label><input id="trailing_stop_pct" type="number" step="0.1"></div>
        <div><label>수수료(%)</label><input id="taker_fee_pct" type="number" step="0.01"></div>
        <div><label>슬리피지(%)</label><input id="slippage_pct" type="number" step="0.01"></div>
        <div><label>최소 기대 순수익(%)</label><input id="min_expected_net_profit_pct" type="number" step="0.1"></div>
        <div><label>BTC 급락 차단 기준(%)</label><input id="btc_crash_5m_pct" type="number" step="0.1"></div>
        <div><label>스캔 종목 수</label><input id="scan_top_markets" type="number" min="1"></div>
        <div><label>최소 24h 거래대금(KRW)</label><input id="min_24h_trade_price_krw" type="number" min="0"></div>
      </div>
      <button onclick="saveSettings()">설정 저장/적용</button>
      <button onclick="loadSettings()">설정 불러오기</button>
      <pre id="settings"></pre>
    </section>
    <section>
      <h2>매매 후보 신호</h2>
      <button onclick="post('/api/scan', {})">후보 분석</button>
      <button onclick="post('/api/ai', {})">AI 분석</button>
      <pre id="signals"></pre>
    </section>
    <section>
      <h2>자금 현황</h2>
      <button onclick="post('/api/portfolio', {})">자금 현황 저장/조회</button>
      <button onclick="get('/api/report', 'portfolio')">HTML 리포트 생성</button>
      <pre id="portfolio"></pre>
    </section>
    <section>
      <h2>기록 / 로그</h2>
      <button onclick="get('/api/logs?limit=30', 'logs')">최근 로그</button>
      <pre id="logs"></pre>
    </section>
  </main>
  <script>
    async function get(path, target) {
      const res = await fetch(path);
      const data = await res.json();
      document.getElementById(target).textContent = JSON.stringify(data, null, 2);
    }
    async function post(path, body) {
      const res = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
      const data = await res.json();
      const target = path.includes('scan') || path.includes('ai') ? 'signals' : path.includes('portfolio') ? 'portfolio' : path.includes('settings') ? 'settings' : 'status';
      document.getElementById(target).textContent = JSON.stringify(data, null, 2);
      loadStatus();
    }
    async function loadStatus() { await get('/api/status', 'status'); }
    async function loadSettings() {
      const res = await fetch('/api/settings');
      const data = await res.json();
      const settings = data.settings || {};
      for (const [key, value] of Object.entries(settings)) {
        const el = document.getElementById(key);
        if (el) el.value = String(value);
      }
      document.getElementById('settings').textContent = JSON.stringify(data, null, 2);
    }
    async function saveSettings() {
      const keys = [
        'ai_enabled','trading_mode','ai_model','bot_interval_seconds','total_budget_krw','max_position_krw',
        'min_position_krw','max_open_positions','daily_loss_limit_krw','stop_after_consecutive_losses',
        'take_profit_pct','stop_loss_pct','trailing_stop_pct','taker_fee_pct','slippage_pct',
        'min_expected_net_profit_pct','btc_crash_5m_pct','scan_top_markets','min_24h_trade_price_krw'
      ];
      const body = {};
      for (const key of keys) {
        const el = document.getElementById(key);
        if (el) body[key] = el.value;
      }
      await post('/api/settings', body);
    }
    async function startConfigured() {
      const mode = document.getElementById('trading_mode')?.value || 'paper';
      await post('/api/start', {mode});
    }
    loadStatus();
    loadSettings();
    setInterval(loadStatus, 10000);
  </script>
</body>
</html>"""

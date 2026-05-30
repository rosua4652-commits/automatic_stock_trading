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
from .storage import read_jsonl
from .upbit import UpbitClient


def serve(host: str = "0.0.0.0", port: int = 8080, interval_seconds: int = 60) -> None:
    config = AppConfig.from_env()
    bot = TradingBot(config, UpbitClient(config.credentials))
    controller = BotController(bot, interval_seconds=interval_seconds)
    ai_client = AIAnalysisClient(config)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_html(_dashboard_html())
            elif parsed.path == "/api/status":
                self._send_json({"ok": True, "status": controller.status()})
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
                started = controller.start(body.get("mode", "paper"))
                self._send_json({"ok": True, "started": started, "status": controller.status()})
            elif parsed.path == "/api/stop":
                controller.stop()
                self._send_json({"ok": True, "status": controller.status()})
            elif parsed.path == "/api/step":
                event = bot.step("paper")
                self._send_json({"ok": True, "event": event})
            elif parsed.path == "/api/scan":
                signals = bot.rank_signals()[:10]
                self._send_json({"ok": True, "signals": signals})
            elif parsed.path == "/api/ai":
                signals = bot.rank_signals()[:1]
                analysis = ai_client.summarize_signal(signals[0], {"source": "web"}) if signals else "No signals"
                self._send_json({"ok": True, "analysis": analysis})
            elif parsed.path == "/api/portfolio":
                snapshot = bot.portfolio_snapshot()
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
  <title>AI Upbit Scalper</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 0; background: #0f172a; color: #e2e8f0; }
    header { padding: 20px 28px; background: #111827; border-bottom: 1px solid #334155; }
    main { padding: 24px; display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 18px; }
    section { background: #111827; border: 1px solid #334155; border-radius: 12px; padding: 18px; }
    button { margin: 4px; padding: 10px 14px; border: 0; border-radius: 8px; background: #2563eb; color: white; cursor: pointer; }
    button.danger { background: #dc2626; }
    button.safe { background: #16a34a; }
    pre { overflow: auto; white-space: pre-wrap; background: #020617; padding: 12px; border-radius: 8px; max-height: 420px; }
    .muted { color: #94a3b8; }
  </style>
</head>
<body>
  <header>
    <h1>AI Upbit Scalper Dashboard</h1>
    <p class="muted">기본은 paper mode입니다. 실거래는 환경변수로 별도 활성화해야 합니다.</p>
  </header>
  <main>
    <section>
      <h2>Bot Control</h2>
      <button class="safe" onclick="post('/api/start', {mode:'paper'})">Paper 지속 실행</button>
      <button onclick="post('/api/step', {})">1회 분석/실행</button>
      <button class="danger" onclick="post('/api/stop', {})">중단</button>
      <button onclick="loadStatus()">상태 새로고침</button>
      <pre id="status">loading...</pre>
    </section>
    <section>
      <h2>Signals</h2>
      <button onclick="post('/api/scan', {})">후보 분석</button>
      <button onclick="post('/api/ai', {})">AI 분석</button>
      <pre id="signals"></pre>
    </section>
    <section>
      <h2>Portfolio</h2>
      <button onclick="post('/api/portfolio', {})">자금 현황 저장/조회</button>
      <button onclick="get('/api/report', 'portfolio')">HTML 리포트 생성</button>
      <pre id="portfolio"></pre>
    </section>
    <section>
      <h2>Logs</h2>
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
      const target = path.includes('scan') || path.includes('ai') ? 'signals' : path.includes('portfolio') ? 'portfolio' : 'status';
      document.getElementById(target).textContent = JSON.stringify(data, null, 2);
      loadStatus();
    }
    async function loadStatus() { await get('/api/status', 'status'); }
    loadStatus();
    setInterval(loadStatus, 10000);
  </script>
</body>
</html>"""

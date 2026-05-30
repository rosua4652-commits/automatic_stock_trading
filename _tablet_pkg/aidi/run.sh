#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8000}"

free_port() {
  local pids
  pids="$(lsof -ti:"$PORT" 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "포트 $PORT 사용 중 — 기존 서버 종료 (PID: $pids)"
    kill $pids 2>/dev/null || true
    sleep 1
    pids="$(lsof -ti:"$PORT" 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      kill -9 $pids 2>/dev/null || true
      sleep 0.5
    fi
  fi
}

if [ ! -d "$ROOT/backend/.venv" ]; then
  python3 -m venv "$ROOT/backend/.venv"
fi
"$ROOT/backend/.venv/bin/pip" install -q -r "$ROOT/backend/requirements.txt"

if [ ! -d "$ROOT/frontend/node_modules" ]; then
  (cd "$ROOT/frontend" && npm install)
fi

(cd "$ROOT/frontend" && npm run build)
free_port
cd "$ROOT/backend"
echo ""
echo "  AIDI → http://127.0.0.1:$PORT"
echo ""
exec "$ROOT/backend/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port "$PORT"

#!/usr/bin/env bash
# Termux — 권장: python run.py (chmod 불필요)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8000}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 없음 → pkg install -y python"
  exit 1
fi

if [ ! -f "$ROOT/frontend/dist/index.html" ]; then
  echo "frontend/dist 없음"
  exit 1
fi

REQ="$ROOT/backend/requirements-termux.txt"
[ -f "$REQ" ] || REQ="$ROOT/backend/requirements.txt"

VENV_ARGS=()
if [ -n "${PREFIX:-}" ] && [[ "$PREFIX" == *com.termux* ]]; then
  pkg install -y python-numpy 2>/dev/null || true
  VENV_ARGS=(--system-site-packages)
fi

if [ ! -d "$ROOT/backend/.venv" ]; then
  echo "가상환경 생성..."
  python3 -m venv "${VENV_ARGS[@]}" "$ROOT/backend/.venv"
fi

echo "패키지 설치 중..."
"$ROOT/backend/.venv/bin/pip" install -q --upgrade pip
"$ROOT/backend/.venv/bin/pip" install -q -r "$REQ"

mkdir -p "$ROOT/backend/data"
cd "$ROOT/backend"
echo ""
echo "  http://127.0.0.1:$PORT"
echo ""
exec "$ROOT/backend/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port "$PORT"

#!/usr/bin/env bash
# 삼성 갤럭시 탭 등 Android — Termux에서 실행 (npm 불필요, dist 포함 가정)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8000}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3가 없습니다."
  echo "  Termux: pkg update && pkg install -y python"
  exit 1
fi

if [ ! -f "$ROOT/frontend/dist/index.html" ]; then
  echo "frontend/dist 가 없습니다. PC용 run.sh 로 빌드한 뒤 다시 압축해 주세요."
  exit 1
fi

if [ ! -d "$ROOT/backend/.venv" ]; then
  echo "가상환경 생성 중..."
  python3 -m venv "$ROOT/backend/.venv"
fi

echo "패키지 설치 중 (처음만 수 분 걸릴 수 있음)..."
"$ROOT/backend/.venv/bin/pip" install -q --upgrade pip
"$ROOT/backend/.venv/bin/pip" install -q -r "$ROOT/backend/requirements.txt"

mkdir -p "$ROOT/backend/data"

cd "$ROOT/backend"
echo ""
echo "  AIDI (태블릿)"
echo "  브라우저(Chrome/Samsung Internet)에서:"
echo "    http://127.0.0.1:$PORT"
echo ""
echo "  종료: Ctrl+C"
echo ""
exec "$ROOT/backend/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port "$PORT"

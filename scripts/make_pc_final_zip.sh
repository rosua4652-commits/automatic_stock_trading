#!/usr/bin/env bash
# PC 최종본 ZIP (dongil-3 폴더 구조용). credentials/venv 제외.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${ROOT}/aidi-pc-dongil3-final.zip"
cd "$ROOT"
if [[ ! -f frontend/dist/index.html ]]; then
  echo "Run: cd frontend && npm run build"
  exit 1
fi
rm -f "$OUT"
zip -r "$OUT" \
  run.bat run.ps1 run.py SETUP_PC.bat sync-pc-from-github.bat check-pc-folder.bat \
  check-build.bat check-upbit-ip.bat probe-upbit.bat update-windows.bat \
  pc-path.txt PC_실행_이폴더.txt PC_최종본_설치.txt WINDOWS_설치안내.md README.md \
  backend/app backend/requirements.txt scripts/probe_upbit.py \
  frontend/dist \
  -x "backend/data/*" "backend/.venv/*" "*__pycache__*" "*.pyc"
echo "Created: $OUT"

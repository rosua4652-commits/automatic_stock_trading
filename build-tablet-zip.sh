#!/usr/bin/env bash
# 태블릿용 zip 빌드 — zip 안에 aidi/ 폴더 + web/ 백업 포함
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PKG="$ROOT/_tablet_pkg/aidi"
OUT="$ROOT/aidi-samsung-tablet.zip"

cd "$ROOT/frontend" && npm run build

rm -rf "$ROOT/_tablet_pkg"
mkdir -p "$PKG/frontend"
cp -r "$ROOT/backend" "$PKG/"
cp -r "$ROOT/frontend/dist" "$PKG/frontend/"
cp -r "$ROOT/frontend/dist" "$PKG/web"
cp "$ROOT/run.py" "$ROOT/run-tablet.sh" "$ROOT/run.bat" "$ROOT/TERMUX_권한해결.txt" \
   "$ROOT/삼성패드_설치안내.md" "$ROOT/WINDOWS_설치안내.md" "$ROOT/README.md" "$ROOT/run.sh" "$PKG/"

cd "$ROOT/_tablet_pkg"
rm -f "$OUT"
zip -r "$OUT" aidi -x '*/__pycache__/*' '*.pyc' '*/.venv/*'

echo ""
echo "생성: $OUT ($(du -h "$OUT" | cut -f1))"
echo "Termux: unzip -o aidi-samsung-tablet.zip -d ~ && cd ~/aidi && python run.py"
unzip -l "$OUT" | grep -E 'aidi/run.py|aidi/frontend/dist/index|aidi/web/index' || true

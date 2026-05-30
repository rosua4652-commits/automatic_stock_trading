#!/usr/bin/env python3
"""
AIDI 실행 (chmod 불필요)
  Termux:  cd ~/aidi && python run.py
  PC:      python3 run.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / "backend" / ".venv"
PIP = VENV / "bin" / "pip"
PY = VENV / "bin" / "python"
REQ = ROOT / "backend" / "requirements-termux.txt"
REQ_DEFAULT = ROOT / "backend" / "requirements.txt"
DIST = ROOT / "frontend" / "dist" / "index.html"
PORT = os.environ.get("PORT", "8000")


def in_termux() -> bool:
    return bool(os.environ.get("PREFIX", "").startswith("/data/data/com.termux"))


def run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, **kwargs)


def main() -> int:
    if not DIST.is_file():
        print("오류: frontend/dist/index.html 없음 — PC에서 npm run build 후 다시 압축하세요.")
        return 1

    py_sys = sys.executable
    if not py_sys:
        print("오류: python3 없음. Termux: pkg install -y python")
        return 1
    print(f"AIDI 폴더: {ROOT}")
    print(f"Python: {py_sys}")

    if in_termux():
        print("\n[Termux] 저장소는 ~/aidi 만 쓰세요. Downloads/SD 에 두면 권한 오류 납니다.\n")

    if not VENV.is_dir():
        print("가상환경 생성...")
        venv_args = [py_sys, "-m", "venv", str(VENV)]
        if in_termux():
            # pkg install python-numpy 한 경우 시스템 numpy 사용
            venv_args.insert(3, "--system-site-packages")
        run(venv_args)

    req = REQ if REQ.is_file() else REQ_DEFAULT
    print("패키지 설치 (처음엔 수 분)...")
    run([str(PIP), "install", "-q", "--upgrade", "pip"])
    run([str(PIP), "install", "-q", "-r", str(req)])

    (ROOT / "backend" / "data").mkdir(parents=True, exist_ok=True)

    print(f"\n  브라우저 → http://127.0.0.1:{PORT}\n  종료: Ctrl+C\n")
    os.chdir(ROOT / "backend")
    os.execv(
        str(PY),
        [str(PY), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", PORT],
    )
    return 0


def shutil_which(cmd: str) -> str | None:
    from shutil import which

    return which(cmd)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        print(f"\n설치 실패 (코드 {e.returncode})")
        if in_termux():
            print(
                "Termux에서 시도:\n"
                "  pkg update && pkg install -y python python-pip python-venv python-numpy\n"
                "  cd ~/aidi && python run.py"
            )
        raise SystemExit(e.returncode)
    except KeyboardInterrupt:
        raise SystemExit(0)

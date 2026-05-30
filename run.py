#!/usr/bin/env python3
"""
AIDI 실행 (chmod 불필요)
  Termux:  cd ~/aidi && python run.py
  PC:      python3 run.py
"""
from __future__ import annotations

import os
import shutil
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
TERMUX_HOME = Path(os.environ.get("HOME", str(Path.home())))
TERMUX_AIDI = TERMUX_HOME / "aidi"


def in_termux() -> bool:
    return bool(os.environ.get("PREFIX", "").startswith("/data/data/com.termux"))


def is_android_shared_storage(path: Path) -> bool:
    """Downloads/SD (/storage/emulated/0) — venv 심볼릭 링크 불가."""
    s = str(path.resolve())
    blocked = (
        "/storage/emulated",
        "/sdcard/",
        "/storage/sdcard",
        "/mnt/sdcard",
        "/storage/self/primary",
    )
    if any(b in s for b in blocked):
        return True
    # Termux 홈은 보통 /data/data/com.termux/files/home
    if s.startswith("/data/data/") and "com.termux" in s:
        return False
    if s.startswith(str(TERMUX_HOME)):
        return False
    return False


def print_storage_fix() -> None:
    print(
        "\n"
        "════════════════════════════════════════════════════\n"
        "  지금 폴더가 다운로드/SD 카드입니다.\n"
        "  여기서는 .venv(가상환경)를 만들 수 없습니다.\n"
        "  (lib -> lib64 Permission denied)\n"
        "════════════════════════════════════════════════════\n"
        "\n"
        "Termux에서 아래를 그대로 복사하세요:\n"
        "\n"
        "  pkg install -y unzip\n"
        "  cp ~/storage/downloads/aidi-samsung-tablet.zip ~/\n"
        "  cd ~\n"
        "  rm -rf ~/aidi\n"
        "  mkdir -p ~/aidi\n"
        "  unzip -o ~/aidi-samsung-tablet.zip -d ~/aidi\n"
        "  cd ~/aidi\n"
        "  python run.py\n"
        "\n"
        f"  (홈 경로 예: {TERMUX_AIDI})\n"
        "\n"
        "지금 경로가 /storage/emulated/0/... 이면 반드시 ~/aidi 로 옮기세요.\n"
    )


def run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, **kwargs)


def ensure_not_shared_storage() -> int | None:
    if not is_android_shared_storage(ROOT):
        return None
    print(f"현재 위치: {ROOT}")
    print_storage_fix()
    return 1


def main() -> int:
    if err := ensure_not_shared_storage():
        return err

    if not DIST.is_file():
        print("오류: frontend/dist/index.html 없음")
        return 1

    py_sys = sys.executable
    print(f"AIDI 폴더: {ROOT}")
    print(f"Python: {py_sys}")

    # 이전에 SD에 만들다 만 .venv 제거
    broken = VENV / "lib64"
    if VENV.is_dir() and is_android_shared_storage(ROOT):
        return 1
    if VENV.is_dir() and not (VENV / "bin" / "python").is_file():
        print("깨진 .venv 삭제 후 다시 생성...")
        shutil.rmtree(VENV, ignore_errors=True)

    if not VENV.is_dir():
        print("가상환경 생성...")
        venv_args = [py_sys, "-m", "venv", str(VENV)]
        if in_termux():
            venv_args.insert(3, "--system-site-packages")
        try:
            run(venv_args)
        except subprocess.CalledProcessError:
            print_storage_fix()
            return 1
        except PermissionError:
            print_storage_fix()
            return 1

    req = REQ if REQ.is_file() else REQ_DEFAULT
    print("패키지 설치 (처음엔 수분)...")
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


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        print(f"\n설치 실패 (코드 {e.returncode})")
        if is_android_shared_storage(ROOT) or in_termux():
            print_storage_fix()
        raise SystemExit(e.returncode)
    except PermissionError as e:
        print(f"\nPermission denied: {e}")
        print_storage_fix()
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(0)

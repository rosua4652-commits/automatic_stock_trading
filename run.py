#!/usr/bin/env python3
"""
AIDI 실행 (chmod 불필요)
  Termux:  cd ~/aidi && python run.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PORT = os.environ.get("PORT", "8000")
TERMUX_HOME = Path(os.environ.get("HOME", str(Path.home())))
TERMUX_AIDI = TERMUX_HOME / "aidi"


def in_termux() -> bool:
    return bool(os.environ.get("PREFIX", "").startswith("/data/data/com.termux"))


def is_android_shared_storage(path: Path) -> bool:
    s = str(path.resolve())
    if any(
        b in s
        for b in (
            "/storage/emulated",
            "/sdcard/",
            "/storage/sdcard",
            "/mnt/sdcard",
            "/storage/self/primary",
        )
    ):
        return True
    if s.startswith("/data/data/") and "com.termux" in s:
        return False
    if s.startswith(str(TERMUX_HOME)):
        return False
    return False


def print_storage_fix() -> None:
    print(
        "\n"
        "════════════════════════════════════════════════════\n"
        "  다운로드/SD(/storage/emulated/0) 에서는 실행 불가\n"
        "  Termux 홈 ~/aidi 에 zip 전체를 풀어야 합니다.\n"
        "════════════════════════════════════════════════════\n"
        "\n"
        "  cp ~/storage/downloads/aidi-samsung-tablet.zip ~/\n"
        "  cd ~\n"
        "  rm -rf ~/aidi\n"
        "  unzip -o ~/aidi-samsung-tablet.zip -d ~\n"
        "  cd ~/aidi\n"
        "  ls frontend/dist/index.html\n"
        "  python run.py\n"
    )


def print_dist_fix(root: Path) -> None:
    print(f"\n현재 run.py 위치: {root}")
    print(f"홈: {TERMUX_HOME}\n")
    print("── 이 폴더 내용 ──")
    try:
        for name in sorted(os.listdir(root))[:30]:
            p = root / name
            mark = "/" if p.is_dir() else ""
            print(f"  {name}{mark}")
    except OSError as e:
        print(f"  (목록 불가: {e})")
    print("\n── 확인 ──")
    checks = [
        root / "frontend" / "dist" / "index.html",
        root / "web" / "index.html",
        TERMUX_HOME / "aidi" / "frontend" / "dist" / "index.html",
        TERMUX_HOME / "frontend" / "dist" / "index.html",
    ]
    for c in checks:
        ok = "OK" if c.is_file() else "없음"
        print(f"  [{ok}] {c}")
    print(
        "\n"
        "해결: zip **전체**를 다시 받아 ~/aidi 에 풀기\n"
        "  (run.py만 복사하면 화면 파일이 없습니다)\n"
        "  unzip -o ~/aidi-samsung-tablet.zip -d ~\n"
        "  cd ~/aidi && ls frontend/dist/index.html\n"
    )


def find_project_root() -> Path:
    """run.py 가 있는 폴더 또는 ~/aidi / 홈에 흩어진 unzip."""
    here = Path(__file__).resolve().parent
    candidates = [
        here,
        here / "aidi",
        TERMUX_HOME / "aidi",
        TERMUX_HOME,
    ]
    seen: set[str] = set()
    for base in candidates:
        key = str(base)
        if key in seen:
            continue
        seen.add(key)
        if (base / "backend" / "app" / "main.py").is_file():
            return base
    return here


def ensure_frontend_dist(root: Path) -> Path:
    """frontend/dist/index.html 없으면 web/ 백업에서 복사."""
    target = root / "frontend" / "dist"
    index = target / "index.html"
    if index.is_file():
        return target

    backups = [
        root / "web",
        root / "dist",
        root.parent / "frontend" / "dist",
        TERMUX_HOME / "frontend" / "dist",
    ]
    for src in backups:
        if (src / "index.html").is_file():
            print(f"화면 파일 복구: {src} → {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(src, target)
            return target

    print_dist_fix(root)
    raise SystemExit(1)


def venv_python(venv: Path) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def venv_pip(venv: Path) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / "pip.exe"
    return venv / "bin" / "pip"


def pick_requirements(root: Path) -> Path:
    if in_termux() and (root / "backend" / "requirements-termux.txt").is_file():
        return root / "backend" / "requirements-termux.txt"
    return root / "backend" / "requirements.txt"


def run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, **kwargs)


def main() -> int:
    root = find_project_root()
    os.chdir(root)

    if is_android_shared_storage(root):
        print(f"현재 위치: {root}")
        print_storage_fix()
        return 1

    ensure_frontend_dist(root)

    venv = root / "backend" / ".venv"
    pip = venv_pip(venv)
    py = venv_python(venv)
    req = pick_requirements(root)

    py_sys = sys.executable
    print(f"AIDI 폴더: {root}")

    if venv.is_dir() and not py.is_file():
        shutil.rmtree(venv, ignore_errors=True)

    if not venv.is_dir():
        print("가상환경 생성...")
        args = [py_sys, "-m", "venv", str(venv)]
        if in_termux():
            args.insert(3, "--system-site-packages")
        try:
            run(args)
        except (subprocess.CalledProcessError, PermissionError):
            if in_termux():
                print_storage_fix()
            return 1

    print("패키지 설치 (처음엔 수분)...")
    run([str(pip), "install", "-q", "--upgrade", "pip"])
    run([str(pip), "install", "-q", "-r", str(req)])

    (root / "backend" / "data").mkdir(parents=True, exist_ok=True)
    host = "127.0.0.1" if in_termux() else "0.0.0.0"
    print(f"\n  브라우저 → http://127.0.0.1:{PORT}\n  종료: Ctrl+C\n")
    os.chdir(root / "backend")
    if sys.platform == "win32":
        subprocess.call(
            [str(py), "-m", "uvicorn", "app.main:app", "--host", host, "--port", PORT]
        )
        return 0
    os.execv(
        str(py),
        [str(py), "-m", "uvicorn", "app.main:app", "--host", host, "--port", PORT],
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        print(f"\n설치 실패 (코드 {e.returncode})")
        if in_termux():
            print_storage_fix()
        raise SystemExit(e.returncode)
    except KeyboardInterrupt:
        raise SystemExit(0)

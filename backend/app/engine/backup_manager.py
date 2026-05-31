"""설정·데이터 백업/복원 (ZIP). API 키는 마스킹."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

from app.models import AppConfig
from app.storage.persistence import DATA_DIR, load_paper_state, load_live_meta, load_backtest_state

BACKUP_FILES = (
    "paper_portfolio.json",
    "live_aidi_meta.json",
    "backtest_accumulator.json",
    "risk_state.json",
    "risk_state_paper.json",
    "risk_state_live.json",
    "user_settings.json",
    "paper_auto_days.json",
    "config_snapshot.json",
)


def _mask_config(cfg: AppConfig) -> dict[str, Any]:
    d = cfg.model_dump()
    for key in (
        "api_access_key",
        "api_secret_key",
        "binance_api_key",
        "binance_api_secret",
    ):
        v = (d.get(key) or "").strip()
        if v:
            d[key] = v[:4] + "…" + ("*" * 8)
    return d


def export_backup_zip(config: AppConfig) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        snap = _mask_config(config)
        zf.writestr(
            "config_snapshot.json",
            json.dumps(snap, ensure_ascii=False, indent=2),
        )
        for name in BACKUP_FILES:
            if name == "config_snapshot.json":
                continue
            path = DATA_DIR / name
            if path.is_file():
                zf.write(path, arcname=name)
    return buf.getvalue()


def import_backup_zip(data: bytes, *, merge: bool = True) -> tuple[int, list[str]]:
    """merge=True: 기존 파일 덮어쓰기. API 키 마스킹본은 config에 적용 안 함."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    notes: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
        for name in zf.namelist():
            base = Path(name).name
            if base not in BACKUP_FILES:
                continue
            if base == "config_snapshot.json":
                notes.append("config_snapshot.json — 설정 화면에서 수동 확인")
                continue
            target = DATA_DIR / base
            if target.exists() and not merge:
                notes.append(f"skip {base} (exists)")
                continue
            target.write_bytes(zf.read(name))
            n += 1
    return n, notes

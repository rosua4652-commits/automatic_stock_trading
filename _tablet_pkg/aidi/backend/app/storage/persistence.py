"""모의 / 실거래 데이터 완전 분리 저장."""

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PAPER_FILE = DATA_DIR / "paper_portfolio.json"
LIVE_META_FILE = DATA_DIR / "live_aidi_meta.json"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_paper_state() -> dict[str, Any] | None:
    ensure_data_dir()
    if not PAPER_FILE.exists():
        return None
    try:
        return json.loads(PAPER_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_paper_state(data: dict[str, Any]) -> None:
    ensure_data_dir()
    PAPER_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_live_meta() -> dict[str, Any]:
    ensure_data_dir()
    if not LIVE_META_FILE.exists():
        return {"positions_meta": {}, "trades": [], "realized_pnl_krw": 0.0}
    try:
        data = json.loads(LIVE_META_FILE.read_text(encoding="utf-8"))
        data.setdefault("positions_meta", {})
        data.setdefault("trades", [])
        return data
    except Exception:
        return {"positions_meta": {}, "trades": [], "realized_pnl_krw": 0.0}


def save_live_meta(data: dict[str, Any]) -> None:
    ensure_data_dir()
    LIVE_META_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clear_live_meta() -> None:
    save_live_meta({"positions_meta": {}, "trades": [], "realized_pnl_krw": 0.0})

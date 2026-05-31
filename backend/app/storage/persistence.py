"""모의 / 실거래 데이터 완전 분리 저장."""

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PAPER_FILE = DATA_DIR / "paper_portfolio.json"
LIVE_META_FILE = DATA_DIR / "live_aidi_meta.json"
BACKTEST_FILE = DATA_DIR / "backtest_accumulator.json"


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


def load_backtest_state() -> dict[str, Any]:
    ensure_data_dir()
    if not BACKTEST_FILE.exists():
        return _default_backtest_state()
    try:
        data = json.loads(BACKTEST_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _default_backtest_state()
        data.setdefault("symbols", {})
        data.setdefault("cycles", 0)
        data.setdefault("best_sl_pct", 0.0)
        data.setdefault("best_tp_pct", 0.0)
        return data
    except Exception:
        return _default_backtest_state()


def save_backtest_state(data: dict[str, Any]) -> None:
    ensure_data_dir()
    BACKTEST_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _default_backtest_state() -> dict[str, Any]:
    return {
        "symbols": {},
        "cycles": 0,
        "best_sl_pct": 0.0,
        "best_tp_pct": 0.0,
        "updated_at": 0.0,
        "learning": {},
        "execution_feedback": [],
    }


def reset_paper_state(initial_balance_krw: float) -> None:
    """모의 잔고·포지션·거래내역 초기화."""
    save_paper_state(
        {
            "cash_krw": float(initial_balance_krw),
            "realized_pnl_krw": 0.0,
            "usdt_krw": 1350.0,
            "positions": {},
            "trades": [],
        }
    )


def clear_paper_state_file() -> None:
    ensure_data_dir()
    if PAPER_FILE.exists():
        PAPER_FILE.unlink()


def reset_backtest_state() -> None:
    """백테스트 누적·학습·체결 피드백 전부 삭제."""
    import time

    data = _default_backtest_state()
    data["updated_at"] = time.time()
    save_backtest_state(data)

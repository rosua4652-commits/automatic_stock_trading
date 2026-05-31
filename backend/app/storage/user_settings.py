"""사용자 설정 — backend/data/user_settings.json (ZIP/git 동기화 시 유지)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.models import AppConfig, TradeMode

USER_SETTINGS_FILE = (
    Path(__file__).resolve().parent.parent.parent / "data" / "user_settings.json"
)

# API 키는 credentials.json 전용
_SECRET_KEYS = frozenset(
    {
        "api_access_key",
        "api_secret_key",
        "binance_api_key",
        "binance_api_secret",
    }
)


def persisted_config_keys() -> list[str]:
    """설정 화면 항목 키 목록 (정렬·비교용)."""
    return sorted(k for k in AppConfig.model_fields if k not in _SECRET_KEYS)


def _ensure_data_dir() -> None:
    USER_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_raw() -> dict[str, Any] | None:
    if not USER_SETTINGS_FILE.is_file():
        return None
    try:
        data = json.loads(USER_SETTINGS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _values_from_raw(raw: dict[str, Any]) -> dict[str, Any]:
    inner = raw.get("values")
    if isinstance(inner, dict):
        return dict(inner)
    return {k: v for k, v in raw.items() if k not in ("schema_keys", "saved_at")}


def _schema_keys_match(stored_keys: list[str] | None, current: list[str]) -> bool:
    if not stored_keys:
        return False
    return sorted(str(k) for k in stored_keys) == sorted(current)


def _coerce_config_values(values: dict[str, Any]) -> dict[str, Any]:
    """Pydantic 검증 전 trade_mode 등 보정."""
    data = dict(values)
    tm = data.get("trade_mode")
    if isinstance(tm, str):
        data["trade_mode"] = TradeMode.LIVE if tm.lower() == "live" else TradeMode.PAPER
    return data


def merge_user_settings_into_config(base: AppConfig | None = None) -> AppConfig:
    """
    저장된 사용자 설정을 AppConfig에 반영.
    - schema_keys 가 현재와 같으면: 저장값 그대로 사용 (업데이트 ZIP/git 과 무관)
    - 항목 추가/삭제 시: 새 항목은 기본값, 기존 항목은 사용자 값 유지 후 저장
    """
    template = base or AppConfig()
    current_keys = persisted_config_keys()
    raw = _load_raw()

    if raw is None:
        return template

    stored_keys = raw.get("schema_keys")
    old_values = _values_from_raw(raw)

    if _schema_keys_match(
        stored_keys if isinstance(stored_keys, list) else None, current_keys
    ):
        merged = {**template.model_dump(), **_coerce_config_values(old_values)}
        try:
            return AppConfig(**merged)
        except Exception:
            pass

    # 스키마 변경 — 마이그레이션
    merged_dict = template.model_dump()
    for key in current_keys:
        if key in old_values:
            merged_dict[key] = old_values[key]
    try:
        cfg = AppConfig(**_coerce_config_values(merged_dict))
    except Exception:
        cfg = template

    save_user_settings(cfg, reason="schema_migrate")
    return cfg


def save_user_settings(cfg: AppConfig, *, reason: str = "user_save") -> None:
    """설정 저장 (API 키 제외)."""
    _ensure_data_dir()
    keys = persisted_config_keys()
    data = cfg.model_dump()
    values = {k: data[k] for k in keys}
    tm = values.get("trade_mode")
    if hasattr(tm, "value"):
        values["trade_mode"] = tm.value

    payload = {
        "schema_keys": keys,
        "values": values,
        "saved_at": time.time(),
        "reason": reason,
    }
    USER_SETTINGS_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def user_settings_status() -> dict[str, Any]:
    """디버그·UI용 — 스키마 일치 여부."""
    current = persisted_config_keys()
    raw = _load_raw()
    if not raw:
        return {"exists": False, "schema_match": False, "path": str(USER_SETTINGS_FILE)}
    stored = raw.get("schema_keys") if isinstance(raw.get("schema_keys"), list) else []
    return {
        "exists": True,
        "schema_match": _schema_keys_match(stored, current),
        "stored_key_count": len(stored),
        "current_key_count": len(current),
        "path": str(USER_SETTINGS_FILE),
    }

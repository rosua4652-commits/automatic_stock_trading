"""API 키 로컬 저장 (git 제외)."""

import json
import time
from pathlib import Path
from typing import Any

from app.models import AppConfig, TradeMode

CRED_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "credentials.json"


def _ensure() -> None:
    CRED_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_credentials() -> dict[str, Any]:
    _ensure()
    if not CRED_FILE.exists():
        return {}
    try:
        return json.loads(CRED_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_credentials(
    exchange: str,
    access_key: str,
    secret_key: str,
    *,
    merge: bool = True,
) -> dict[str, Any]:
    """비어 있지 않은 키만 갱신 (merge=True면 기존 값 유지)."""
    _ensure()
    current = load_credentials() if merge else {}
    ak = access_key.strip()
    sk = secret_key.strip()
    if ak:
        current["api_access_key"] = ak
    if sk:
        current["api_secret_key"] = sk
    if exchange:
        current["exchange"] = exchange
    current["updated_at"] = time.time()
    CRED_FILE.write_text(
        json.dumps(current, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return current


def mask_key(key: str, show: int = 4) -> str:
    if not key or len(key) <= show * 2:
        return "****" if key else ""
    return f"{key[:show]}****{key[-show:]}"


def apply_credentials_to_config(cfg: AppConfig) -> AppConfig:
    cred = load_credentials()
    if not cred:
        return cfg
    data = cfg.model_dump()
    if cred.get("api_access_key"):
        data["api_access_key"] = cred["api_access_key"]
    if cred.get("api_secret_key"):
        data["api_secret_key"] = cred["api_secret_key"]
    if cred.get("exchange"):
        data["exchange"] = cred["exchange"]
    return AppConfig(**data)


def config_for_response(cfg: AppConfig) -> dict[str, Any]:
    """응답용 — 시크릿 마스킹."""
    d = cfg.model_dump()
    if d.get("api_access_key"):
        d["api_access_key_masked"] = mask_key(d["api_access_key"])
    if d.get("api_secret_key"):
        d["api_secret_key_masked"] = mask_key(d["api_secret_key"])
    d["api_access_key"] = ""
    d["api_secret_key"] = ""
    d["binance_api_key"] = ""
    d["binance_api_secret"] = ""
    d["has_saved_keys"] = bool(load_credentials().get("api_access_key"))
    return d


def get_active_keys(cfg: AppConfig) -> tuple[str, str]:
    ak = cfg.api_access_key or cfg.binance_api_key
    sk = cfg.api_secret_key or cfg.binance_api_secret
    return ak.strip(), sk.strip()


def has_api_keys(cfg: AppConfig) -> bool:
    ak, sk = get_active_keys(cfg)
    return bool(ak and sk)

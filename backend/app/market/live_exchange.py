"""실거래 — 업비트 전용."""

from typing import Any

from app.market.upbit_client import upbit_client
from app.models import AppConfig
from app.storage.credentials import get_active_keys


async def test_exchange_connection(cfg: AppConfig) -> dict[str, Any]:
    ak, sk = get_active_keys(cfg)
    if (cfg.exchange or "upbit").lower() != "upbit":
        return {"ok": False, "message": "AIDI는 업비트(KRW)만 지원합니다."}
    upbit_client.configure(ak, sk)
    return await upbit_client.test_connection()


async def close_all() -> None:
    await upbit_client.close()

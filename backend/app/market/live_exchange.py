"""실거래 거래소 라우터 (Upbit / Binance)."""

from typing import Any

from app.market.binance_live import binance_live
from app.market.upbit_client import symbol_to_upbit, upbit_client, upbit_to_symbol
from app.models import AppConfig
from app.storage.credentials import get_active_keys


async def test_exchange_connection(cfg: AppConfig) -> dict[str, Any]:
    ak, sk = get_active_keys(cfg)
    if cfg.exchange == "upbit":
        upbit_client.configure(ak, sk)
        return await upbit_client.test_connection()
    binance_live.configure(ak, sk, testnet=cfg.use_testnet)
    await binance_live._signed_get("/api/v3/account")
    return {
        "ok": True,
        "exchange": "binance",
        "message": "Binance 계정 연결 성공",
    }


async def close_all() -> None:
    await binance_live.close()
    await upbit_client.close()

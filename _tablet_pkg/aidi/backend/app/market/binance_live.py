"""Binance Spot signed API (실거래)."""

import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import httpx

MAIN_BASE = "https://api.binance.com"
TESTNET_BASE = "https://testnet.binance.vision"


class BinanceLiveClient:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._api_key = ""
        self._api_secret = ""
        self._base = MAIN_BASE
        self._use_testnet = False

    def configure(self, api_key: str, api_secret: str, testnet: bool = False) -> None:
        self._api_key = api_key.strip()
        self._api_secret = api_secret.strip()
        self._use_testnet = testnet
        self._base = TESTNET_BASE if testnet else MAIN_BASE
        if self._client:
            self._client.headers["X-MBX-APIKEY"] = self._api_key

    def is_configured(self) -> bool:
        return bool(self._api_key and self._api_secret)

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"X-MBX-APIKEY": self._api_key},
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _sign(self, params: dict[str, Any]) -> dict[str, Any]:
        params = {k: v for k, v in params.items() if v is not None}
        params["timestamp"] = int(time.time() * 1000)
        query = urlencode(params)
        sig = hmac.new(
            self._api_secret.encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = sig
        return params

    async def _signed_get(self, path: str, params: dict | None = None) -> Any:
        if not self.is_configured():
            raise RuntimeError("API 키가 설정되지 않았습니다")
        client = await self._ensure_client()
        p = self._sign(params or {})
        resp = await client.get(f"{self._base}{path}", params=p)
        if resp.status_code >= 400:
            raise RuntimeError(f"Binance API: {resp.text}")
        return resp.json()

    async def _signed_post(self, path: str, params: dict) -> Any:
        if not self.is_configured():
            raise RuntimeError("API 키가 설정되지 않았습니다")
        client = await self._ensure_client()
        p = self._sign(params)
        resp = await client.post(f"{self._base}{path}", params=p)
        if resp.status_code >= 400:
            raise RuntimeError(f"Binance API: {resp.text}")
        return resp.json()

    async def ping_auth(self) -> bool:
        try:
            await self._signed_get("/api/v3/account")
            return True
        except Exception:
            return False

    async def account(self) -> dict[str, Any]:
        return await self._signed_get("/api/v3/account")

    async def my_trades(self, symbol: str, limit: int = 50) -> list[dict]:
        try:
            return await self._signed_get(
                "/api/v3/myTrades",
                {"symbol": symbol, "limit": limit},
            )
        except Exception:
            return []

    async def market_buy_quote(self, symbol: str, quote_usdt: float) -> dict:
        """USDT 금액으로 시장가 매수."""
        return await self._signed_post(
            "/api/v3/order",
            {
                "symbol": symbol,
                "side": "BUY",
                "type": "MARKET",
                "quoteOrderQty": f"{quote_usdt:.8f}".rstrip("0").rstrip("."),
            },
        )

    async def market_sell_qty(self, symbol: str, quantity: float) -> dict:
        """수량 기준 시장가 매도."""
        return await self._signed_post(
            "/api/v3/order",
            {
                "symbol": symbol,
                "side": "SELL",
                "type": "MARKET",
                "quantity": f"{quantity:.8f}".rstrip("0").rstrip("."),
            },
        )


binance_live = BinanceLiveClient()

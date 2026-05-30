"""Upbit REST API (JWT)."""

import hashlib
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.market.ipv4_http import ipv4_async_client
from app.market.network_info import get_outbound_public_ip

UPBIT_API = "https://api.upbit.com"


async def _parse_upbit_error(text: str) -> RuntimeError:
    if "no_authorization_ip" in text:
        ip = await get_outbound_public_ip()
        ip_hint = (
            f" 지금 이 PC에서 업비트로 나가는 IP: {ip} — 업비트 Open API 키에 이 주소(IPv4)를 등록하세요."
            if ip
            else " cmd에서 curl ifconfig.me 로 공인 IP 확인 후 업비트에 등록하세요."
        )
        return RuntimeError(
            "업비트 API: 허용 IP가 등록되지 않았습니다."
            + ip_hint
            + " (VPN/핫스팟 사용 중이면 IP가 달라집니다. 등록 후 1~2분 기다린 뒤 설정 → 연결 테스트)"
        )
    if "invalid_access_key" in text:
        return RuntimeError("업비트 API: Access Key가 올바르지 않습니다.")
    if "invalid_secret_key" in text:
        return RuntimeError("업비트 API: Secret Key가 올바르지 않습니다.")
    return RuntimeError(f"Upbit: {text}")


class UpbitClient:
    def __init__(self) -> None:
        self._access = ""
        self._secret = ""
        self._client: httpx.AsyncClient | None = None

    def configure(self, access_key: str, secret_key: str) -> None:
        self._access = access_key.strip()
        self._secret = secret_key.strip()
        self._client = None

    def is_configured(self) -> bool:
        return bool(self._access and self._secret)

    async def _ensure(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = ipv4_async_client(
                base_url=UPBIT_API,
                timeout=25.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _token(self, query: dict | None = None) -> str:
        payload: dict[str, Any] = {
            "access_key": self._access,
            "nonce": str(uuid.uuid4()),
        }
        if query:
            qs = urlencode(query, doseq=True).encode()
            h = hashlib.sha512()
            h.update(qs)
            payload["query_hash"] = h.hexdigest()
            payload["query_hash_alg"] = "SHA512"
        token = jwt.encode(payload, self._secret, algorithm="HS256")
        return token if isinstance(token, str) else token.decode()

    async def _auth_get(self, path: str, params: dict | None = None) -> Any:
        if not self.is_configured():
            raise RuntimeError("Upbit API 키가 없습니다")
        client = await self._ensure()
        headers = {"Authorization": f"Bearer {self._token(params)}"}
        resp = await client.get(path, params=params, headers=headers)
        if resp.status_code >= 400:
            raise await _parse_upbit_error(resp.text)
        return resp.json()

    async def _auth_post(self, path: str, body: dict) -> Any:
        if not self.is_configured():
            raise RuntimeError("Upbit API 키가 없습니다")
        client = await self._ensure()
        headers = {"Authorization": f"Bearer {self._token(body)}"}
        resp = await client.post(path, json=body, headers=headers)
        if resp.status_code >= 400:
            raise await _parse_upbit_error(resp.text)
        return resp.json()

    async def test_connection(self) -> dict[str, Any]:
        accounts = await self._auth_get("/v1/accounts")
        krw = 0.0
        coins = 0
        for a in accounts:
            cur = a.get("currency", "")
            bal = float(a.get("balance", 0))
            if cur == "KRW":
                krw = bal
            elif bal > 0:
                coins += 1
        return {
            "ok": True,
            "exchange": "upbit",
            "krw_balance": krw,
            "coin_count": coins,
            "accounts": len(accounts),
        }

    async def accounts(self) -> list[dict]:
        return await self._auth_get("/v1/accounts")

    async def tickers(self, markets: list[str]) -> dict[str, dict]:
        if not markets:
            return {}
        client = await self._ensure()
        resp = await client.get(
            "/v1/ticker",
            params={"markets": ",".join(markets)},
        )
        resp.raise_for_status()
        rows = resp.json()
        return {r["market"]: r for r in rows}

    async def market_buy_krw(self, market: str, price_krw: float) -> dict:
        return await self._auth_post(
            "/v1/orders",
            {
                "market": market,
                "side": "bid",
                "ord_type": "price",
                "price": str(int(price_krw)),
            },
        )

    async def market_sell(self, market: str, volume: float) -> dict:
        return await self._auth_post(
            "/v1/orders",
            {
                "market": market,
                "side": "ask",
                "ord_type": "market",
                "volume": f"{volume:.8f}".rstrip("0").rstrip("."),
            },
        )


def symbol_to_upbit(symbol: str) -> str:
    s = symbol.upper()
    if s.startswith("KRW-"):
        return s
    base = s.replace("USDT", "").replace("KRW", "")
    return f"KRW-{base}"


def upbit_to_symbol(market: str) -> str:
    if market.startswith("KRW-"):
        return market.replace("KRW-", "") + "USDT"
    return market


upbit_client = UpbitClient()

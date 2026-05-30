"""Upbit REST API (JWT)."""

import hashlib
import json
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.market.ipv4_http import outbound_ipv4_via_same_stack, shared_upbit_client
from app.market.network_info import get_outbound_public_ip
from app.storage.credentials import mask_key

UPBIT_API = "https://api.upbit.com"


def _parse_upbit_error_body(text: str) -> tuple[str, str]:
    """(error_name, message) from Upbit JSON or raw text."""
    try:
        data = json.loads(text)
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            return str(err.get("name") or ""), str(err.get("message") or text)
    except Exception:
        pass
    return "", text


async def _parse_upbit_error(text: str, access_hint: str = "") -> RuntimeError:
    name, msg = _parse_upbit_error_body(text)
    key_note = f" (AIDI Access Key: {access_hint})" if access_hint else ""
    if name == "no_authorization_ip" or "no_authorization_ip" in text:
        ip = await outbound_ipv4_via_same_stack() or await get_outbound_public_ip()
        ip_hint = (
            f" AIDI→업비트 나가는 IP: {ip}."
            if ip
            else " cmd: curl -4 https://api.ipify.org 로 IPv4 확인."
        )
        return RuntimeError(
            "업비트 API: 허용 IP 오류(no_authorization_ip)."
            + ip_hint
            + key_note
            + " 업비트 Open API에서 **이 Access Key** 행에 위 IP가 등록됐는지 확인하세요."
            + " (다른 키에 IP만 등록한 경우 동일 증상 · VPN/IPv6이면 IP가 달라질 수 있음)"
        )
    if name == "invalid_access_key" or "invalid_access_key" in text:
        return RuntimeError(
            "업비트 API: Access Key가 올바르지 않습니다." + key_note
        )
    if name == "invalid_secret_key" or "invalid_secret_key" in text:
        return RuntimeError(
            "업비트 API: Secret Key가 올바르지 않습니다 (Access와 짝이 맞는지 확인)."
            + key_note
        )
    if name in ("invalid_query_payload", "jwt_verification"):
        return RuntimeError(f"업비트 API: {name or '요청 오류'} — {msg}{key_note}")
    if name:
        return RuntimeError(f"업비트 API [{name}]: {msg}{key_note}")
    return RuntimeError(f"Upbit: {msg or text}{key_note}")


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
            self._client = shared_upbit_client()
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
            raise await _parse_upbit_error(resp.text, mask_key(self._access, 4))
        return resp.json()

    async def _auth_post(self, path: str, body: dict) -> Any:
        if not self.is_configured():
            raise RuntimeError("Upbit API 키가 없습니다")
        client = await self._ensure()
        headers = {"Authorization": f"Bearer {self._token(body)}"}
        resp = await client.post(path, json=body, headers=headers)
        if resp.status_code >= 400:
            raise await _parse_upbit_error(resp.text, mask_key(self._access, 4))
        return resp.json()

    async def probe_accounts(self) -> dict[str, Any]:
        """연결 테스트용 — 업비트 원문 오류·IP 포함."""
        if not self.is_configured():
            return {"ok": False, "message": "키 없음"}
        outbound = await outbound_ipv4_via_same_stack() or await get_outbound_public_ip()
        hint = mask_key(self._access, 4)
        client = await self._ensure()
        headers = {"Authorization": f"Bearer {self._token()}"}
        resp = await client.get("/v1/accounts", headers=headers)
        name, msg = _parse_upbit_error_body(resp.text)
        out: dict[str, Any] = {
            "ok": resp.status_code < 400,
            "status_code": resp.status_code,
            "upbit_error_name": name or None,
            "upbit_error_message": msg if resp.status_code >= 400 else None,
            "access_key_hint": hint,
            "access_key_len": len(self._access),
            "secret_key_len": len(self._secret),
            "outbound_ipv4_stack": outbound or "",
        }
        if resp.status_code >= 400:
            out["raw_body"] = resp.text[:400]
        else:
            rows = resp.json()
            out["accounts"] = len(rows) if isinstance(rows, list) else 0
        return out

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

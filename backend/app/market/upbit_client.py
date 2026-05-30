"""Upbit REST API (JWT) — 공식 Exchange API 인증."""

from typing import Any

import httpx

from app.market.ipv4_http import outbound_ipv4_via_same_stack, shared_upbit_client
from app.market.network_info import get_outbound_public_ip
from app.market.upbit_auth import auth_headers, build_query_string
from app.market.upbit_client_errors import parse_upbit_error
from app.storage.credentials import mask_key

UPBIT_API = "https://api.upbit.com"


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

    def _headers(self, query_string: str = "") -> dict[str, str]:
        return auth_headers(self._access, self._secret, query_string)

    async def _auth_get(self, path: str, params: dict | None = None) -> Any:
        if not self.is_configured():
            raise RuntimeError("Upbit API 키가 없습니다")
        client = await self._ensure()
        qs = build_query_string(params)
        headers = self._headers(qs)
        if qs:
            resp = await client.get(f"{path}?{qs}", headers=headers)
        else:
            resp = await client.get(path, headers=headers)
        if resp.status_code >= 400:
            raise await parse_upbit_error(resp.text, mask_key(self._access, 4))
        return resp.json()

    async def _auth_post(self, path: str, body: dict) -> Any:
        if not self.is_configured():
            raise RuntimeError("Upbit API 키가 없습니다")
        client = await self._ensure()
        qs = build_query_string(body)
        headers = self._headers(qs)
        headers["Content-Type"] = "application/json"
        resp = await client.post(path, json=body, headers=headers)
        if resp.status_code >= 400:
            raise await parse_upbit_error(resp.text, mask_key(self._access, 4))
        return resp.json()

    async def probe_accounts(self) -> dict[str, Any]:
        if not self.is_configured():
            return {"ok": False, "message": "키 없음"}
        outbound = await outbound_ipv4_via_same_stack() or await get_outbound_public_ip()
        hint = mask_key(self._access, 4)
        client = await self._ensure()
        headers = self._headers("")
        resp = await client.get("/v1/accounts", headers=headers)
        from app.market.upbit_client_errors import parse_upbit_error_body

        name, msg = parse_upbit_error_body(resp.text)
        out: dict[str, Any] = {
            "ok": resp.status_code < 400,
            "status_code": resp.status_code,
            "jwt_algorithm": "HS512",
            "upbit_error_name": name or None,
            "upbit_error_message": msg if resp.status_code >= 400 else None,
            "access_key_hint": hint,
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
        from app.market.upbit_markets import get_upbit_krw_markets

        allowed = await get_upbit_krw_markets()
        valid = [m for m in markets if m in allowed]
        if not valid:
            return {}
        client = await self._ensure()
        out: dict[str, dict] = {}
        chunk = 100
        for i in range(0, len(valid), chunk):
            part = valid[i : i + chunk]
            resp = await client.get(
                "/v1/ticker",
                params={"markets": ",".join(part)},
            )
            resp.raise_for_status()
            for r in resp.json():
                out[r["market"]] = r
        return out

    async def market_buy_krw(self, market: str, price_krw: float) -> dict:
        body = {
            "market": market,
            "side": "bid",
            "ord_type": "price",
            "price": str(int(price_krw)),
        }
        return await self._auth_post("/v1/orders", body)

    async def market_sell(self, market: str, volume: float) -> dict:
        vol = f"{volume:.8f}".rstrip("0").rstrip(".")
        body = {
            "market": market,
            "side": "ask",
            "ord_type": "market",
            "volume": vol,
        }
        return await self._auth_post("/v1/orders", body)


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

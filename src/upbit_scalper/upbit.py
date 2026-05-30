from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any

from .config import UpbitCredentials


class UpbitError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candle:
    market: str
    timestamp: str
    opening_price: float
    high_price: float
    low_price: float
    trade_price: float
    candle_acc_trade_volume: float
    candle_acc_trade_price: float

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> "Candle":
        return cls(
            market=item["market"],
            timestamp=item.get("candle_date_time_kst") or item.get("candle_date_time_utc", ""),
            opening_price=float(item["opening_price"]),
            high_price=float(item["high_price"]),
            low_price=float(item["low_price"]),
            trade_price=float(item["trade_price"]),
            candle_acc_trade_volume=float(item["candle_acc_trade_volume"]),
            candle_acc_trade_price=float(item["candle_acc_trade_price"]),
        )


class UpbitClient:
    def __init__(
        self,
        credentials: UpbitCredentials | None = None,
        base_url: str = "https://api.upbit.com",
        timeout: int = 15,
    ) -> None:
        self.credentials = credentials or UpbitCredentials("", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_markets(self, quote_currency: str = "KRW") -> list[str]:
        rows = self._request("GET", "/v1/market/all", {"isDetails": "true"}, auth=False)
        prefix = f"{quote_currency.upper()}-"
        return [
            row["market"]
            for row in rows
            if row.get("market", "").startswith(prefix) and row.get("market_event", {}).get("warning") is False
        ]

    def get_tickers(self, markets: list[str]) -> list[dict[str, Any]]:
        if not markets:
            return []
        rows: list[dict[str, Any]] = []
        for offset in range(0, len(markets), 100):
            chunk = markets[offset : offset + 100]
            rows.extend(self._request("GET", "/v1/ticker", {"markets": ",".join(chunk)}, auth=False))
        return rows

    def get_minute_candles(self, market: str, unit: int = 5, count: int = 200) -> list[Candle]:
        if unit not in {1, 3, 5, 10, 15, 30, 60, 240}:
            raise ValueError("Unsupported Upbit minute candle unit")
        rows = self._request("GET", f"/v1/candles/minutes/{unit}", {"market": market, "count": count}, auth=False)
        candles = [Candle.from_api(row) for row in rows]
        candles.reverse()
        return candles

    def get_accounts(self) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/accounts", auth=True)

    def place_market_buy(self, market: str, krw_amount: float) -> dict[str, Any]:
        params = {"market": market, "side": "bid", "ord_type": "price", "price": f"{krw_amount:.0f}"}
        return self._request("POST", "/v1/orders", params, auth=True)

    def place_market_sell(self, market: str, volume: float) -> dict[str, Any]:
        params = {"market": market, "side": "ask", "ord_type": "market", "volume": f"{volume:.8f}"}
        return self._request("POST", "/v1/orders", params, auth=True)

    def get_order(self, uuid_value: str) -> dict[str, Any]:
        return self._request("GET", "/v1/order", {"uuid": uuid_value}, auth=True)

    def cancel_order(self, uuid_value: str) -> dict[str, Any]:
        return self._request("DELETE", "/v1/order", {"uuid": uuid_value}, auth=True)

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        auth: bool = False,
    ) -> Any:
        params = params or {}
        method = method.upper()
        query = urllib.parse.urlencode(params, doseq=True)
        url = f"{self.base_url}{path}"
        body: bytes | None = None
        headers = {"Accept": "application/json"}

        if method == "GET" and query:
            url = f"{url}?{query}"
        elif method in {"POST", "DELETE"}:
            body = query.encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        if auth:
            headers["Authorization"] = f"Bearer {self._jwt(query if params else None)}"

        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload) if payload else {}
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = {"raw": payload}
            raise UpbitError(f"Upbit HTTP {exc.code}: {parsed}") from exc
        except urllib.error.URLError as exc:
            raise UpbitError(f"Upbit connection failed: {exc}") from exc

    def _jwt(self, query_string: str | None = None) -> str:
        if not self.credentials.is_configured:
            raise UpbitError("UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY are required for private APIs")

        payload: dict[str, Any] = {
            "access_key": self.credentials.access_key,
            "nonce": str(uuid.uuid4()),
        }
        if query_string:
            query_hash = hashlib.sha512(query_string.encode()).hexdigest()
            payload["query_hash"] = query_hash
            payload["query_hash_alg"] = "SHA512"

        header = {"alg": "HS512", "typ": "JWT"}
        message = f"{_b64url_json(header)}.{_b64url_json(payload)}"
        signature = hmac.new(self.credentials.secret_key.encode(), message.encode(), hashlib.sha512).digest()
        return f"{message}.{_b64url(signature)}"


def _b64url_json(data: dict[str, Any]) -> str:
    return _b64url(json.dumps(data, separators=(",", ":")).encode())


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

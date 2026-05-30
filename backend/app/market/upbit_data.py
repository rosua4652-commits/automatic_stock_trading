"""업비트 공개 API — 시세·캔들·스캔 (바이낸스 미사용)."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.market.upbit_client import symbol_to_upbit, upbit_to_symbol
from app.market.upbit_markets import get_upbit_krw_markets

STABLE_BASES = {
    "USDT",
    "USDC",
    "BUSD",
    "DAI",
    "TUSD",
    "FDUSD",
    "EUR",
    "GBP",
    "KRW",
}
RISKY_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")
RISKY_SUBSTRINGS = ("3L", "3S", "5L", "5S")

_INTERVAL_PATHS: dict[str, tuple[str, str | int]] = {
    "1s": ("seconds", ""),
    "1m": ("minutes", 1),
    "15m": ("minutes", 15),
    "1h": ("minutes", 60),
    "4h": ("minutes", 240),
    "1d": ("days", ""),
}


def is_safe_krw_base(base: str) -> bool:
    base = base.upper()
    if not base or base in STABLE_BASES:
        return False
    if any(base.endswith(s) for s in RISKY_SUFFIXES):
        return False
    if any(x in base for x in RISKY_SUBSTRINGS):
        return False
    return True


def _ticker_to_internal(row: dict[str, Any], usdt_krw: float) -> dict[str, Any]:
    """내부 포맷: symbol 키는 BTCUSDT, 가격은 USDT 환산."""
    rate = max(usdt_krw, 1.0)
    price_krw = float(row.get("trade_price") or 0)
    vol_krw = float(row.get("acc_trade_price_24h") or 0)
    chg = float(row.get("signed_change_rate") or 0) * 100.0
    return {
        "lastPrice": str(price_krw / rate),
        "priceChangePercent": str(chg),
        "quoteVolume": str(vol_krw / rate),
        "trade_price_krw": price_krw,
    }


def _candle_row(c: dict[str, Any]) -> list:
    ts = int(c.get("timestamp") or 0)
    return [
        ts,
        str(c.get("opening_price", 0)),
        str(c.get("high_price", 0)),
        str(c.get("low_price", 0)),
        str(c.get("trade_price", 0)),
        str(c.get("candle_acc_trade_volume", 0)),
    ]


class UpbitDataClient:
    async def close(self) -> None:
        pass

    async def usdt_krw_rate(self) -> float:
        from app.market.ipv4_http import shared_upbit_client

        client = shared_upbit_client()
        try:
            resp = await client.get("/v1/ticker", params={"markets": "KRW-USDT"})
            resp.raise_for_status()
            rows = resp.json()
            if rows:
                return float(rows[0].get("trade_price") or 1350.0)
        except Exception:
            pass
        return 1350.0

    async def tickers_24h(self) -> dict[str, dict[str, Any]]:
        from app.market.ipv4_http import shared_upbit_client

        markets = sorted(await get_upbit_krw_markets())
        if not markets:
            return {}
        rate = await self.usdt_krw_rate()
        client = shared_upbit_client()
        out: dict[str, dict[str, Any]] = {}
        chunk = 100
        for i in range(0, len(markets), chunk):
            part = markets[i : i + chunk]
            resp = await client.get(
                "/v1/ticker",
                params={"markets": ",".join(part)},
            )
            resp.raise_for_status()
            for row in resp.json():
                market = row.get("market", "")
                if not market.startswith("KRW-"):
                    continue
                base = market.replace("KRW-", "")
                if not is_safe_krw_base(base):
                    continue
                sym = upbit_to_symbol(market)
                out[sym] = _ticker_to_internal(row, rate)
        return out

    async def klines(
        self, symbol: str, interval: str = "1h", limit: int = 168
    ) -> list[list]:
        from app.market.ipv4_http import shared_upbit_client

        market = symbol_to_upbit(symbol.upper())
        allowed = await get_upbit_krw_markets()
        if market not in allowed:
            return []

        iv = interval.lower()
        path_spec = _INTERVAL_PATHS.get(iv, ("minutes", 60))
        kind, unit = path_spec
        client = shared_upbit_client()
        if kind == "seconds":
            url = "/v1/candles/seconds"
            params: dict[str, Any] = {"market": market, "count": min(limit, 200)}
        elif kind == "days":
            url = "/v1/candles/days"
            params = {"market": market, "count": min(limit, 200)}
        else:
            url = f"/v1/candles/minutes/{unit}"
            params = {"market": market, "count": min(limit, 200)}

        resp = await client.get(url, params=params)
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list):
            return []
        raw = [_candle_row(c) for c in reversed(rows)]
        return raw

    async def price(self, symbol: str) -> float:
        tickers = await self.tickers_24h()
        t = tickers.get(symbol.upper())
        if t:
            return float(t["lastPrice"])
        return 0.0


upbit_data = UpbitDataClient()

# 앱 전역 시세·캔들 (업비트 전용)
market = upbit_data

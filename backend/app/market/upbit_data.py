"""업비트 공개 API — 시세·캔들·스캔 (바이낸스 미사용)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

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

# 업비트 REST rate limit — 전 종목 ticker 는 캐시 + 소량 배치
_TICKERS_CACHE: tuple[float, dict[str, dict[str, Any]]] | None = None
_TICKERS_LOCK = asyncio.Lock()
_USDT_KRW_CACHE: tuple[float, float] | None = None
_TICKERS_TTL_SEC = 25.0
_TICKER_CHUNK_SIZE = 35
_TICKER_CHUNK_DELAY_SEC = 0.18
_KLINES_CACHE: dict[str, tuple[float, list[list]]] = {}
_KLINES_LOCK = asyncio.Lock()
_CANDLE_SEM = asyncio.Semaphore(1)
_LAST_CANDLE_REQ = 0.0
_CANDLE_MIN_GAP_SEC = 0.45


def _klines_ttl_sec(interval: str) -> float:
    iv = interval.lower()
    if iv == "1s":
        return 8.0
    if iv == "1m":
        return 35.0
    if iv == "15m":
        return 50.0
    return 90.0


async def _throttle_candle_api() -> None:
    global _LAST_CANDLE_REQ
    now = time.time()
    wait = _CANDLE_MIN_GAP_SEC - (now - _LAST_CANDLE_REQ)
    if wait > 0:
        await asyncio.sleep(wait)
    _LAST_CANDLE_REQ = time.time()


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


def _stale_tickers() -> dict[str, dict[str, Any]] | None:
    global _TICKERS_CACHE
    if _TICKERS_CACHE:
        return _TICKERS_CACHE[1]
    return None


async def _get_with_retry(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    last: httpx.Response | None = None
    for attempt in range(5):
        resp = await client.get(url, **kwargs)
        last = resp
        if resp.status_code == 429:
            from app.engine.market_health import report_rate_limit

            report_rate_limit(retry_sec=min(2.0, 0.35 * (2**attempt)))
            await asyncio.sleep(min(2.0, 0.35 * (2**attempt)))
            continue
        return resp
    return last  # type: ignore[return-value]


async def _fetch_ticker_rows(
    client: httpx.AsyncClient, market_list: list[str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(0, len(market_list), _TICKER_CHUNK_SIZE):
        part = market_list[i : i + _TICKER_CHUNK_SIZE]
        resp = await _get_with_retry(
            client,
            "/v1/ticker",
            params={"markets": ",".join(part)},
        )
        if resp.status_code == 429:
            from app.engine.market_health import report_rate_limit

            report_rate_limit("업비트 ticker 429")
            raise httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=resp.request,
                response=resp,
            )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            rows.extend(data)
        if i + _TICKER_CHUNK_SIZE < len(market_list):
            await asyncio.sleep(_TICKER_CHUNK_DELAY_SEC)
    return rows


class UpbitDataClient:
    async def close(self) -> None:
        pass

    async def usdt_krw_rate(self) -> float:
        global _USDT_KRW_CACHE
        now = time.time()
        if _USDT_KRW_CACHE and now - _USDT_KRW_CACHE[0] < 30:
            return _USDT_KRW_CACHE[1]

        from app.market.ipv4_http import shared_upbit_client

        client = shared_upbit_client()
        try:
            resp = await _get_with_retry(
                client, "/v1/ticker", params={"markets": "KRW-USDT"}
            )
            resp.raise_for_status()
            rows = resp.json()
            if rows:
                rate = float(rows[0].get("trade_price") or 1350.0)
                _USDT_KRW_CACHE = (now, rate)
                return rate
        except Exception:
            pass
        return _USDT_KRW_CACHE[1] if _USDT_KRW_CACHE else 1350.0

    async def _build_tickers_dict(
        self, markets: list[str] | None = None
    ) -> dict[str, dict[str, Any]]:
        from app.market.ipv4_http import shared_upbit_client

        if markets is None:
            markets = sorted(await get_upbit_krw_markets())
        if not markets:
            return {}

        rate = await self.usdt_krw_rate()
        client = shared_upbit_client()
        out: dict[str, dict[str, Any]] = {}
        try:
            rows = await _fetch_ticker_rows(client, markets)
        except Exception:
            stale = _stale_tickers()
            if stale:
                return stale
            raise

        for row in rows:
            market = row.get("market", "")
            if not market.startswith("KRW-"):
                continue
            base = market.replace("KRW-", "")
            if not is_safe_krw_base(base):
                continue
            sym = upbit_to_symbol(market)
            out[sym] = _ticker_to_internal(row, rate)
        return out

    async def tickers_24h(self) -> dict[str, dict[str, Any]]:
        global _TICKERS_CACHE
        now = time.time()
        if _TICKERS_CACHE and now - _TICKERS_CACHE[0] < _TICKERS_TTL_SEC:
            return _TICKERS_CACHE[1]

        async with _TICKERS_LOCK:
            now = time.time()
            if _TICKERS_CACHE and now - _TICKERS_CACHE[0] < _TICKERS_TTL_SEC:
                return _TICKERS_CACHE[1]
            try:
                out = await self._build_tickers_dict()
                _TICKERS_CACHE = (time.time(), out)
                return out
            except Exception:
                stale = _stale_tickers()
                if stale:
                    return stale
                raise

    async def tickers_for_symbols(
        self,
        symbols: list[str],
        *,
        fresh: bool = False,
    ) -> dict[str, dict[str, Any]]:
        """탭·보유 종목만 조회 (전 종목 ticker 호출 방지). fresh=True: 캐시 무시."""
        if not symbols:
            return {}
        markets: list[str] = []
        allowed = await get_upbit_krw_markets()
        for sym in symbols:
            m = symbol_to_upbit(sym.upper())
            if m in allowed:
                markets.append(m)
        if not markets:
            return {}
        if fresh or len(markets) <= 25:
            try:
                return await self._build_tickers_dict(markets)
            except Exception:
                stale = _stale_tickers()
                if stale:
                    return {s: stale[s] for s in symbols if s in stale}
                return {}
        all_t = await self.tickers_24h()
        return {s: all_t[s] for s in symbols if s in all_t}

    def get_cached_klines(self, symbol: str, interval: str) -> list[list] | None:
        key = f"{symbol.upper()}:{interval.lower()}"
        hit = _KLINES_CACHE.get(key)
        if hit:
            return hit[1]
        return None

    async def klines(
        self, symbol: str, interval: str = "1h", limit: int = 168
    ) -> list[list]:
        from app.market.ipv4_http import shared_upbit_client

        sym = symbol.upper()
        market = symbol_to_upbit(sym)
        allowed = await get_upbit_krw_markets()
        if market not in allowed:
            return []

        iv = interval.lower()
        cache_key = f"{sym}:{iv}"
        ttl = _klines_ttl_sec(iv)
        now = time.time()
        cached = _KLINES_CACHE.get(cache_key)
        if cached and now - cached[0] < ttl:
            return cached[1]

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

        async with _CANDLE_SEM:
            async with _KLINES_LOCK:
                cached = _KLINES_CACHE.get(cache_key)
                now = time.time()
                if cached and now - cached[0] < ttl:
                    return cached[1]
                await _throttle_candle_api()
                try:
                    resp = await _get_with_retry(client, url, params=params)
                except httpx.HTTPStatusError as e:
                    if cached:
                        return cached[1]
                    if e.response is not None and e.response.status_code == 429:
                        return []
                    raise
                if resp.status_code == 429:
                    if cached:
                        return cached[1]
                    return []
                if resp.status_code >= 400:
                    if cached:
                        return cached[1]
                    resp.raise_for_status()
                rows = resp.json()
                if not isinstance(rows, list):
                    raw: list[list] = []
                else:
                    raw = [_candle_row(c) for c in reversed(rows)]
                _KLINES_CACHE[cache_key] = (time.time(), raw)
                return raw

    async def price(self, symbol: str) -> float:
        t = await self.tickers_for_symbols([symbol.upper()])
        row = t.get(symbol.upper())
        if row:
            return float(row["lastPrice"])
        return 0.0


upbit_data = UpbitDataClient()

# 앱 전역 시세·캔들 (업비트 전용)
market = upbit_data

"""업비트 KRW 마켓 목록 — 바이낸스 USDT 전용 종목 주문 방지."""

from __future__ import annotations

import time

from app.market.upbit_client import symbol_to_upbit

_cache: set[str] | None = None
_cache_at: float = 0.0
_TTL_SEC = 300.0


async def get_upbit_krw_markets(*, force: bool = False) -> set[str]:
    global _cache, _cache_at
    now = time.time()
    if not force and _cache is not None and now - _cache_at < _TTL_SEC:
        return _cache

    from app.market.ipv4_http import shared_upbit_client

    client = shared_upbit_client()
    resp = await client.get("/v1/market/all")
    resp.raise_for_status()
    markets: set[str] = set()
    for row in resp.json():
        if not isinstance(row, dict):
            continue
        m = str(row.get("market") or "")
        if m.startswith("KRW-"):
            markets.add(m)
    _cache = markets
    _cache_at = now
    return markets


def resolve_upbit_market(symbol: str, markets: set[str]) -> str | None:
    """BROCCOLI714USDT → KRW-BROCCOLI714; 업비트에 없으면 None."""
    market = symbol_to_upbit(symbol.upper())
    return market if market in markets else None


async def is_tradable_on_upbit(symbol: str) -> bool:
    markets = await get_upbit_krw_markets()
    return resolve_upbit_market(symbol, markets) is not None


async def filter_symbols_for_upbit(symbols: list[str]) -> list[str]:
    markets = await get_upbit_krw_markets()
    out: list[str] = []
    for s in symbols:
        sym = s.upper()
        if resolve_upbit_market(sym, markets):
            out.append(sym)
    return out


def invalidate_upbit_market_cache() -> None:
    global _cache, _cache_at
    _cache = None
    _cache_at = 0.0

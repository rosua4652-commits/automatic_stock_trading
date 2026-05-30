from typing import Any

from app.market.data_provider import market_data

STABLE_BASES = {
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "EUR", "GBP",
    "PAX", "USDP", "AEUR", "UST", "SUSD",
}
RISKY_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")
RISKY_SUBSTRINGS = ("3L", "3S", "5L", "5S")


class BinanceClient:
    async def close(self) -> None:
        await market_data.close()

    async def exchange_info(self) -> list[dict[str, Any]]:
        return await market_data.exchange_info()

    async def tickers_24h(self) -> dict[str, dict[str, Any]]:
        return await market_data.tickers_24h()

    async def klines(self, symbol: str, interval: str = "1h", limit: int = 168) -> list[list]:
        return await market_data.klines(symbol, interval, limit)

    async def price(self, symbol: str) -> float:
        tickers = await self.tickers_24h()
        t = tickers.get(symbol)
        if t:
            return float(t["lastPrice"])
        return 0.0

    def is_safe_usdt_pair(self, sym_info: dict[str, Any]) -> bool:
        if sym_info.get("quoteAsset") != "USDT":
            return False
        if sym_info.get("status") != "TRADING":
            return False
        if not sym_info.get("isSpotTradingAllowed", True):
            return False
        base = sym_info.get("baseAsset", "")
        if base in STABLE_BASES:
            return False
        if any(base.endswith(s) for s in RISKY_SUFFIXES):
            return False
        if any(x in base for x in RISKY_SUBSTRINGS):
            return False
        # filter micro-lot / weird permissions
        for f in sym_info.get("filters", []):
            if f.get("filterType") == "NOTIONAL":
                min_notional = float(f.get("minNotional", 0))
                if min_notional > 15:
                    return False
        return True

    async def usdt_krw_rate(self) -> float:
        return await market_data.usdt_krw_rate()


binance = BinanceClient()

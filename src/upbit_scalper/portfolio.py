from __future__ import annotations

from dataclasses import dataclass

from .upbit import UpbitClient


@dataclass(frozen=True)
class AssetValuation:
    currency: str
    market: str | None
    balance: float
    locked: float
    avg_buy_price: float
    current_price: float
    value_krw: float
    cost_basis_krw: float
    unrealized_pnl_krw: float
    unrealized_pnl_pct: float
    allocation_pct: float = 0.0


@dataclass(frozen=True)
class PortfolioSnapshot:
    total_value_krw: float
    cash_krw: float
    invested_value_krw: float
    unrealized_pnl_krw: float
    unrealized_pnl_pct: float
    assets: list[AssetValuation]


class PortfolioManager:
    def __init__(self, client: UpbitClient, quote_currency: str = "KRW") -> None:
        self.client = client
        self.quote_currency = quote_currency

    def snapshot(self) -> PortfolioSnapshot:
        accounts = self.client.get_accounts()
        currencies = [row.get("currency", "") for row in accounts]
        markets = [f"{self.quote_currency}-{currency}" for currency in currencies if currency and currency != self.quote_currency]
        ticker_map = {
            row["market"]: float(row["trade_price"])
            for row in self.client.get_tickers(markets)
        } if markets else {}

        assets: list[AssetValuation] = []
        cash_krw = 0.0
        invested_value = 0.0
        total_cost = 0.0
        unrealized = 0.0

        for row in accounts:
            currency = row.get("currency", "")
            balance = float(row.get("balance") or 0)
            locked = float(row.get("locked") or 0)
            amount = balance + locked
            avg_buy_price = float(row.get("avg_buy_price") or 0)

            if currency == self.quote_currency:
                cash_krw += amount
                assets.append(
                    AssetValuation(
                        currency=currency,
                        market=None,
                        balance=balance,
                        locked=locked,
                        avg_buy_price=1.0,
                        current_price=1.0,
                        value_krw=amount,
                        cost_basis_krw=amount,
                        unrealized_pnl_krw=0.0,
                        unrealized_pnl_pct=0.0,
                    )
                )
                continue

            market = f"{self.quote_currency}-{currency}"
            current_price = ticker_map.get(market, avg_buy_price)
            value = amount * current_price
            cost_basis = amount * avg_buy_price if avg_buy_price > 0 else 0.0
            pnl = value - cost_basis if cost_basis else 0.0
            pnl_pct = (pnl / cost_basis * 100) if cost_basis else 0.0
            invested_value += value
            total_cost += cost_basis
            unrealized += pnl
            assets.append(
                AssetValuation(
                    currency=currency,
                    market=market,
                    balance=balance,
                    locked=locked,
                    avg_buy_price=avg_buy_price,
                    current_price=current_price,
                    value_krw=value,
                    cost_basis_krw=cost_basis,
                    unrealized_pnl_krw=pnl,
                    unrealized_pnl_pct=pnl_pct,
                )
            )

        total_value = cash_krw + invested_value
        with_allocations = [
            AssetValuation(
                **{
                    **asset.__dict__,
                    "allocation_pct": (asset.value_krw / total_value * 100) if total_value else 0.0,
                }
            )
            for asset in assets
        ]
        unrealized_pct = (unrealized / total_cost * 100) if total_cost else 0.0
        return PortfolioSnapshot(
            total_value_krw=total_value,
            cash_krw=cash_krw,
            invested_value_krw=invested_value,
            unrealized_pnl_krw=unrealized,
            unrealized_pnl_pct=unrealized_pct,
            assets=sorted(with_allocations, key=lambda item: item.value_krw, reverse=True),
        )

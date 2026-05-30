import unittest

from upbit_scalper.config import RiskSettings
from upbit_scalper.strategy import MarketContext, ScalpingStrategy
from upbit_scalper.upbit import Candle


def candle(index: int, close: float, volume: float = 100.0) -> Candle:
    return Candle(
        market="KRW-TEST",
        timestamp=f"2026-01-01T00:{index:02d}:00",
        opening_price=close * 0.995,
        high_price=close * 1.002,
        low_price=close * 0.992,
        trade_price=close,
        candle_acc_trade_volume=volume,
        candle_acc_trade_price=volume * close,
    )


class StrategyTests(unittest.TestCase):
    def test_market_risk_off_blocks_entry(self):
        candles = [candle(index, 100 + index * 0.1) for index in range(90)]
        strategy = ScalpingStrategy(RiskSettings())
        signal = strategy.evaluate("KRW-TEST", candles, MarketContext(btc_5m_change_pct=-5))
        self.assertFalse(signal.should_enter)
        self.assertEqual(signal.strategy, "market_risk_off")

    def test_strong_breakout_can_create_entry_plan(self):
        candles = [candle(index, 100 + index * 0.05, 100) for index in range(85)]
        candles.extend(
            [
                candle(85, 105.0, 100),
                candle(86, 105.3, 100),
                candle(87, 105.6, 100),
                candle(88, 105.8, 100),
                candle(89, 108.0, 500),
            ]
        )
        strategy = ScalpingStrategy(RiskSettings())
        signal = strategy.evaluate("KRW-TEST", candles, MarketContext(btc_5m_change_pct=0.1))
        self.assertGreaterEqual(signal.score, 50)
        if signal.should_enter:
            self.assertIsNotNone(signal.plan)


if __name__ == "__main__":
    unittest.main()

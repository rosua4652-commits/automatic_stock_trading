import unittest

from upbit_scalper.indicators import bollinger, ema, rsi, sma


class IndicatorTests(unittest.TestCase):
    def test_sma_calculates_period_average(self):
        self.assertEqual(sma([1, 2, 3, 4], 3), [None, None, 2.0, 3.0])

    def test_ema_starts_with_sma_seed(self):
        result = ema([1, 2, 3, 4], 3)
        self.assertEqual(result[:2], [None, None])
        self.assertAlmostEqual(result[2], 2.0)
        self.assertAlmostEqual(result[3], 3.0)

    def test_rsi_handles_all_gains(self):
        result = rsi([1, 2, 3, 4, 5], period=3)
        self.assertEqual(result[-1], 100.0)

    def test_bollinger_returns_matching_lengths(self):
        values = [float(index) for index in range(30)]
        middle, upper, lower = bollinger(values)
        self.assertEqual(len(middle), len(values))
        self.assertEqual(len(upper), len(values))
        self.assertEqual(len(lower), len(values))
        self.assertIsNotNone(middle[-1])


if __name__ == "__main__":
    unittest.main()

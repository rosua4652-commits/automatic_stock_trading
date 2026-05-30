import unittest

from upbit_scalper.config import AppConfig, RiskSettings, UpbitCredentials
from upbit_scalper.settings_advisor import analyze_investment_settings


def config_with_risk(risk: RiskSettings) -> AppConfig:
    return AppConfig(
        credentials=UpbitCredentials("", ""),
        risk=risk,
        trading_mode="paper",
        live_trading_enabled=False,
        quote_currency="KRW",
        scan_top_markets=30,
        min_24h_trade_price_krw=1_000_000_000,
        ai_enabled=True,
        settings_advisor_enabled=True,
        cursor_api_key="test",
        ai_base_url="http://example.invalid",
        ai_model="test-model",
    )


class SettingsAdvisorTests(unittest.TestCase):
    def test_detects_oversized_position(self):
        advice = analyze_investment_settings(
            config_with_risk(RiskSettings(total_budget_krw=50_000, max_position_krw=30_000)),
            interval_seconds=60,
        )
        self.assertLess(advice.safety_score, 100)
        self.assertIn("max_position_krw", advice.suggested_overrides)

    def test_balanced_defaults_have_no_critical_findings(self):
        advice = analyze_investment_settings(config_with_risk(RiskSettings()), interval_seconds=60)
        self.assertTrue(all(finding.severity != "critical" for finding in advice.findings))


if __name__ == "__main__":
    unittest.main()

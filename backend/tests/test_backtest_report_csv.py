from app.engine.backtest_report import backtest_report_csv, build_backtest_report


def test_backtest_report_csv_has_header_and_top_symbols():
    text = backtest_report_csv(build_backtest_report())
    assert "top_symbols" in text
    assert "symbols_in_store" in text
    assert "data_maturity_pct" in text

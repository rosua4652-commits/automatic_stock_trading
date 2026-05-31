from app.util.numbers import as_float


def test_as_float_from_dict():
    assert as_float({"take_profit_pct": 5.87}) == 5.87
    assert as_float({"nested": 1}, default=3.0) == 3.0


def test_as_float_dict_prefers_tp_keys():
    assert as_float({"stop_loss_pct": 3.2, "take_profit_pct": 5.5}) == 5.5
    assert as_float({"sl": 2.5}) == 2.5

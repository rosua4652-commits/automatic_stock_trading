"""user_settings 스키마 동일 시 유지 / 변경 시 마이그레이션."""

from app.models import AppConfig
from app.storage import user_settings as us


def test_schema_match_keeps_user_values(tmp_path, monkeypatch):
    path = tmp_path / "user_settings.json"
    monkeypatch.setattr(us, "USER_SETTINGS_FILE", path)
    keys = us.persisted_config_keys()
    path.write_text(
        '{"schema_keys": '
        + str(keys).replace("'", '"')
        + ', "values": {"stop_loss_pct": 4.44, "trade_mode": "paper"}}',
        encoding="utf-8",
    )
    cfg = us.merge_user_settings_into_config(AppConfig())
    assert cfg.stop_loss_pct == 4.44


def test_schema_change_migrates_and_adds_defaults(tmp_path, monkeypatch):
    path = tmp_path / "user_settings.json"
    monkeypatch.setattr(us, "USER_SETTINGS_FILE", path)
    path.write_text(
        '{"schema_keys": ["trade_mode", "stop_loss_pct"], '
        '"values": {"stop_loss_pct": 3.5, "trade_mode": "live"}}',
        encoding="utf-8",
    )
    cfg = us.merge_user_settings_into_config(AppConfig())
    assert cfg.stop_loss_pct == 3.5
    assert cfg.trade_mode.value == "live"
    assert path.is_file()
    saved = path.read_text(encoding="utf-8")
    assert "schema_keys" in saved

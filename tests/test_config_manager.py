"""config.json の読み書き・サニタイズの回帰テスト。"""

import json

import config_manager as cm


def test_sanitize_port_and_screenshot_fields() -> None:
    c = cm.AppConfig(port=999999, screenshot_width=50, screenshot_height=50, screenshot_quality=200)
    cm.ConfigManager._sanitize_config(c)
    assert c.port == 65535
    assert c.screenshot_width == 320
    assert c.screenshot_height == 240
    assert c.screenshot_quality == 100


def test_load_unknown_keys_ignored(tmp_path, monkeypatch) -> None:
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(
            {"host": "h", "port": 4455, "future_key": 123},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cm, "CONFIG_FILE", str(cfg_path))
    monkeypatch.setattr(cm, "CONFIG_BACKUP", str(tmp_path / "config.json.bak"))
    c = cm.ConfigManager.load()
    assert c.host == "h"
    assert not hasattr(c, "future_key")


def test_atomic_save_and_recover_from_backup(tmp_path, monkeypatch) -> None:
    cfg_path = tmp_path / "config.json"
    bak_path = tmp_path / "config.json.bak"
    monkeypatch.setattr(cm, "CONFIG_FILE", str(cfg_path))
    monkeypatch.setattr(cm, "CONFIG_BACKUP", str(bak_path))

    cm.ConfigManager.save(cm.AppConfig(host="first", port=4455))
    cm.ConfigManager.save(cm.AppConfig(host="second", port=4456))
    cfg_path.write_text("{broken json", encoding="utf-8")
    c2 = cm.ConfigManager.load()
    assert c2.host == "first"

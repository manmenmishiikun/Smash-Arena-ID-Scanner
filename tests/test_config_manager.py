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


def test_sanitize_extension_bridge_port_separate_from_obs_port() -> None:
    c = cm.AppConfig(port=4455, extension_bridge_port=999999)
    cm.ConfigManager._sanitize_config(c)
    assert c.port == 4455
    assert c.extension_bridge_port == 65535


def test_sanitize_detection_fields() -> None:
    c = cm.AppConfig(
        detection_confirm_needed=0,
        detection_poll_fast_sec=0.001,
        detection_poll_slow_sec=500.0,
    )
    cm.ConfigManager._sanitize_config(c)
    assert c.detection_confirm_needed == 1
    assert c.detection_poll_fast_sec == 0.05
    assert c.detection_poll_slow_sec == 120.0


def test_sanitize_detection_poll_slow_not_below_fast() -> None:
    c = cm.AppConfig(detection_poll_fast_sec=5.0, detection_poll_slow_sec=1.0)
    cm.ConfigManager._sanitize_config(c)
    assert c.detection_poll_fast_sec == 5.0
    assert c.detection_poll_slow_sec == 5.0


def test_app_config_to_detection_config() -> None:
    c = cm.AppConfig(detection_confirm_needed=3, detection_poll_fast_sec=0.5, detection_poll_slow_sec=2.0)
    cm.ConfigManager._sanitize_config(c)
    d = c.to_detection_config()
    assert d.confirm_needed == 3
    assert d.poll_fast == 0.5
    assert d.poll_slow == 2.0


def test_sanitize_extension_bridge_port_invalid_falls_back() -> None:
    c = cm.AppConfig(extension_bridge_port="bad")  # type: ignore[arg-type]
    cm.ConfigManager._sanitize_config(c)
    assert c.extension_bridge_port == cm.DEFAULT_EXTENSION_BRIDGE_PORT
    assert c.port == 4455


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

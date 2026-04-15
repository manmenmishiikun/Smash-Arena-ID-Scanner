import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, fields

from obs_capture import ObsConnectionConfig
from room_id_detector import DetectionConfig

logger = logging.getLogger(__name__)

CONFIG_FILE = "config.json"
CONFIG_BACKUP = "config.json.bak"

# OBS とは無関係。`AppConfig.extension_bridge_port` の既定・サニタイズ失敗時のフォールバック。
DEFAULT_EXTENSION_BRIDGE_PORT = 2206
MIN_DETECTION_POLL_FAST_SEC = 0.2


@dataclass
class AppConfig:
    host: str = "localhost"
    port: int = 4455
    password: str = ""
    target_source: str = ""
    auto_start: bool = False
    always_on_top: bool = False
    sound_enabled: bool = True
    # OBS GetSourceScreenshot の解像度・品質（負荷と認識率のトレードオフ）
    screenshot_width: int = 1920
    screenshot_height: int = 1080
    screenshot_quality: int = 80
    screenshot_format: str = "jpg"  # "jpg" or "png"
    # Chrome 拡張連携（127.0.0.1 の SSE。OBS の host/port とは別物）
    extension_bridge_enabled: bool = False
    extension_bridge_port: int = DEFAULT_EXTENSION_BRIDGE_PORT
    # 部屋ID確定（`RoomIdDetector`）。GUI 未露出だが config.json で上書き可能
    detection_confirm_needed: int = 2
    detection_poll_fast_sec: float = 1.0
    detection_poll_slow_sec: float = 3.0

    def to_obs_connection_config(self) -> ObsConnectionConfig:
        """OBS WebSocket 接続用の設定に変換（ホスト等の重複指定を避ける）。"""
        return ObsConnectionConfig(
            host=self.host,
            port=self.port,
            password=self.password,
        )

    def to_detection_config(self) -> DetectionConfig:
        """`RoomIdDetector` 用。値は `ConfigManager._sanitize_config` 済みを想定。"""
        return DetectionConfig(
            confirm_needed=self.detection_confirm_needed,
            poll_fast=self.detection_poll_fast_sec,
            poll_slow=self.detection_poll_slow_sec,
        )


class ConfigManager:
    @staticmethod
    def _app_config_from_json_dict(data: dict) -> AppConfig:
        """JSON オブジェクトから既知フィールドだけ拾って `AppConfig` を構築する。"""
        known_keys = {f.name for f in fields(AppConfig)}
        filtered = {k: v for k, v in data.items() if k in known_keys}
        return ConfigManager._sanitize_config(AppConfig(**filtered))

    @staticmethod
    def _sanitize_config(c: AppConfig) -> AppConfig:
        try:
            c.port = max(1, min(65535, int(c.port)))
        except (TypeError, ValueError):
            c.port = 4455
        try:
            c.screenshot_width = max(320, min(3840, int(c.screenshot_width)))
            c.screenshot_height = max(240, min(2160, int(c.screenshot_height)))
            c.screenshot_quality = max(1, min(100, int(c.screenshot_quality)))
        except (TypeError, ValueError):
            c.screenshot_width = 1920
            c.screenshot_height = 1080
            c.screenshot_quality = 80
        fmt = (c.screenshot_format or "jpg").strip().lower()
        c.screenshot_format = fmt if fmt in ("jpg", "png") else "jpg"
        try:
            ebp = int(c.extension_bridge_port)
            c.extension_bridge_port = max(1, min(65535, ebp))
        except (TypeError, ValueError):
            c.extension_bridge_port = DEFAULT_EXTENSION_BRIDGE_PORT
        try:
            cn = int(c.detection_confirm_needed)
            c.detection_confirm_needed = max(1, min(20, cn))
        except (TypeError, ValueError):
            c.detection_confirm_needed = 2
        try:
            pf = float(c.detection_poll_fast_sec)
            c.detection_poll_fast_sec = max(MIN_DETECTION_POLL_FAST_SEC, min(60.0, pf))
        except (TypeError, ValueError):
            c.detection_poll_fast_sec = 1.0
        try:
            ps = float(c.detection_poll_slow_sec)
            c.detection_poll_slow_sec = max(0.1, min(120.0, ps))
        except (TypeError, ValueError):
            c.detection_poll_slow_sec = 3.0
        if c.detection_poll_slow_sec < c.detection_poll_fast_sec:
            c.detection_poll_slow_sec = c.detection_poll_fast_sec
        return c

    @staticmethod
    def load() -> AppConfig:
        if not os.path.exists(CONFIG_FILE):
            return AppConfig()
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ConfigManager._app_config_from_json_dict(data)
        except Exception as e:
            logger.warning("設定の読み込みに失敗しました: %s", e)
            if os.path.exists(CONFIG_BACKUP):
                try:
                    with open(CONFIG_BACKUP, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    logger.info("バックアップ %s から復元を試みました。", CONFIG_BACKUP)
                    return ConfigManager._app_config_from_json_dict(data)
                except Exception as e2:
                    logger.warning("バックアップからの読み込みも失敗: %s", e2)
            return AppConfig()

    @staticmethod
    def save(config: AppConfig) -> None:
        """原子的に保存（途中失敗で config.json が壊れにくい）。"""
        ConfigManager._sanitize_config(config)
        directory = os.path.dirname(os.path.abspath(CONFIG_FILE)) or "."
        try:
            if os.path.exists(CONFIG_FILE):
                try:
                    os.replace(CONFIG_FILE, CONFIG_BACKUP)
                except OSError:
                    logger.debug("既存設定のバックアップ置換に失敗（無視して続行）", exc_info=True)

            fd, tmp_path = tempfile.mkstemp(
                prefix=".config_",
                suffix=".tmp.json",
                dir=directory,
                text=True,
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(asdict(config), f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, CONFIG_FILE)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            logger.error("設定の保存に失敗しました: %s", e)

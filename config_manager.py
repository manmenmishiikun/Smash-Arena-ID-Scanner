import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass

from obs_capture import ObsConnectionConfig

logger = logging.getLogger(__name__)

CONFIG_FILE = "config.json"
CONFIG_BACKUP = "config.json.bak"


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

    def to_obs_connection_config(self) -> ObsConnectionConfig:
        """OBS WebSocket 接続用の設定に変換（ホスト等の重複指定を避ける）。"""
        return ObsConnectionConfig(
            host=self.host,
            port=self.port,
            password=self.password,
        )


class ConfigManager:
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
        return c

    @staticmethod
    def load() -> AppConfig:
        if not os.path.exists(CONFIG_FILE):
            return AppConfig()
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            known_keys = {f.name for f in AppConfig.__dataclass_fields__.values()}
            filtered = {k: v for k, v in data.items() if k in known_keys}
            return ConfigManager._sanitize_config(AppConfig(**filtered))
        except Exception as e:
            logger.warning("設定の読み込みに失敗しました: %s", e)
            if os.path.exists(CONFIG_BACKUP):
                try:
                    with open(CONFIG_BACKUP, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    known_keys = {f.name for f in AppConfig.__dataclass_fields__.values()}
                    filtered = {k: v for k, v in data.items() if k in known_keys}
                    logger.info("バックアップ %s から復元を試みました。", CONFIG_BACKUP)
                    return ConfigManager._sanitize_config(AppConfig(**filtered))
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

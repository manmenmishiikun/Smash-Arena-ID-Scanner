"""
obs_capture.py
OBS WebSocket v5 接続・スクリーンショット取得モジュール

使用ライブラリ: obsws-python (pip install obsws-python)
接続: OBS WebSocket v5 プロトコル (OBS 28.0 以降で標準搭載)

GetSourceScreenshot リクエストで特定ソースの画像を取得するため、
キャプチャボードの排他制御を回避しつつ、配信オーバーレイの映り込みもなし。
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import cv2
import numpy as np

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# テスト用の接続設定（実際の値に置き換えてください）
# ---------------------------------------------------------------------------

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 4455
DEFAULT_PASSWORD = ""  # OBS WebSocket の設定で決めたパスワード


# ---------------------------------------------------------------------------
# OBSCaptureクラス
# ---------------------------------------------------------------------------


@dataclass
class ObsConnectionConfig:
    """OBS WebSocket の接続設定をまとめたデータクラス。"""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    password: str = DEFAULT_PASSWORD


def decode_screenshot_payload(
    raw_data: str,
    *,
    imread_flags: int = cv2.IMREAD_COLOR,
) -> Optional[np.ndarray]:
    """
    OBS の image_data 文字列を BGR ndarray にデコードする（テスト・単体利用向け）。

    Returns:
        成功時 BGR 画像、デコード失敗時 None（接続状態は変更しない）
    """
    if not raw_data or not isinstance(raw_data, str):
        return None
    _, sep, payload = raw_data.partition("base64,")
    if sep:
        raw_data = payload
    raw_data = raw_data.strip()
    if not raw_data:
        return None
    try:
        try:
            img_bytes = base64.b64decode(raw_data, validate=True)
        except TypeError:
            img_bytes = base64.b64decode(raw_data)
    except binascii.Error:
        logger.debug("スクリーンショット payload の base64 が不正です。")
        return None
    img_array = np.frombuffer(img_bytes, dtype=np.uint8)
    frame = cv2.imdecode(img_array, imread_flags)
    if frame is None:
        logger.debug("cv2.imdecode が画像を返しませんでした。")
    return frame


class OBSCapture:
    """
    OBS WebSocket v5 を使って特定ソースのスクリーンショットを取得するクラス。

    使い方:
        async with OBSCapture(config) as cap:
            sources = await cap.get_source_list()
            frame = await cap.get_source_screenshot("Switch")
    """

    def __init__(self, config: ObsConnectionConfig):
        self._config = config
        self._client = None

    @property
    def is_connected(self) -> bool:
        """OBS WebSocket への接続が有効かどうかを返す。"""
        return self._client is not None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.disconnect()

    def _connect_sync(self) -> None:
        import obsws_python as obs

        self._client = obs.ReqClient(
            host=self._config.host,
            port=self._config.port,
            password=self._config.password,
            timeout=10,
        )
        logger.info("OBS WebSocket に接続しました: %s:%s", self._config.host, self._config.port)

    async def connect(self) -> None:
        """OBS WebSocket に接続する。"""
        await asyncio.to_thread(self._connect_sync)

    def _disconnect_sync(self) -> None:
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                logger.exception("OBS WebSocket 切断時に例外が発生しました。")
            self._client = None
            logger.info("OBS WebSocket を切断しました。")

    async def disconnect(self) -> None:
        """OBS WebSocket から切断する。"""
        await asyncio.to_thread(self._disconnect_sync)

    def _get_source_list_sync(self) -> list[str]:
        assert self._client is not None
        resp = self._client.get_scene_item_list(
            self._client.get_current_program_scene().current_program_scene_name
        )
        return [item["sourceName"] for item in resp.scene_items]

    async def get_source_list(self) -> list[str]:
        """
        OBS の現在シーン内にある映像ソースの名前一覧を返す。
        GUIのプルダウンメニュー用。
        """
        if not self._client:
            return []
        try:
            return await asyncio.to_thread(self._get_source_list_sync)
        except Exception:
            logger.exception("ソース一覧取得に失敗しました（接続は維持します）。")
            return []

    def _get_source_screenshot_sync(
        self,
        source_name: str,
        width: int,
        height: int,
        image_format: str,
        quality: int,
    ) -> Optional[np.ndarray]:
        assert self._client is not None
        resp = self._client.get_source_screenshot(
            name=source_name,
            img_format=image_format,
            width=width,
            height=height,
            quality=quality,
        )
        raw_data = resp.image_data
        frame = decode_screenshot_payload(raw_data)
        return frame

    async def get_source_screenshot(
        self,
        source_name: str,
        width: int = 1920,
        height: int = 1080,
        image_format: str = "jpg",
        quality: int = 80,
    ) -> Optional[np.ndarray]:
        """
        指定ソース名の画像を OBS から取得し、BGR numpy 配列で返す。

        Args:
            source_name: OBS ソース名（例: "Switch"）
            width, height: 取得解像度（デフォルトは 1920x1080。OBS 側でダウンスケールされる）
            image_format: "jpg" or "png"
            quality: JPEG品質 (0-100)

        Returns:
            BGR numpy 配列 / 失敗時は None
        """
        if not self._client:
            return None
        try:
            return await asyncio.to_thread(
                self._get_source_screenshot_sync,
                source_name,
                width,
                height,
                image_format,
                quality,
            )
        except Exception as e:
            logger.error(
                "スクリーンショット取得で接続エラー (OBS が閉じられた可能性): %s",
                e,
            )
            if self._client:
                try:
                    self._client.disconnect()
                except Exception:
                    logger.debug("disconnect 中の例外を無視", exc_info=True)
                self._client = None
            return None

"""
バックグラウンド OCR ワーカー（OBS 取得 → 画像処理 → WinRT OCR → 部屋ID確定）。
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Callable, Optional, Tuple

import pyperclip

from clipboard_history_win import try_remove_text_from_clipboard_history
from config_manager import AppConfig
from image_processor import ImageProcessor
from ocr_engine import WinRTOcrEngine
from obs_capture import OBSCapture
from pipeline_profile import PipelineProfiler
from room_id_detector import RoomIdDetector

logger = logging.getLogger(__name__)

# `stop_worker` 後に長い asyncio.sleep でスレッド終了が遅れないよう区切る秒（`gui` とは独立）
_SLEEP_SLICE_SEC = 0.1


class OCRWorker(threading.Thread):
    """OBS キャプチャ〜OCR〜確定までを単一スレッドの asyncio ループで回す。

    GUI からは `is_monitoring` / `has_connected` を操作し、コールバックはメインスレッドへ
    `after(0, …)` でマーシャルされる想定（ワーカー側はブロックしない）。
    """

    def __init__(
        self,
        config: AppConfig,
        on_status: Callable[[str], None],
        on_sources: Callable[[list[str]], None],
        on_id_found: Callable[[str], None],
        on_disconnected: Callable[[], None],
        template_1080p: str,
        template_720p: Optional[str],
        on_detection_lamps: Optional[Callable[[bool, bool], None]] = None,
        on_confirmed_id_bridge: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(daemon=True)
        self.config = config
        self.on_status = on_status
        self.on_sources = on_sources
        self.on_id_found = on_id_found
        self.on_disconnected = on_disconnected
        self._on_confirmed_id_bridge = on_confirmed_id_bridge
        self._on_detection_lamps = on_detection_lamps or (lambda _r, _i: None)
        self._template_1080p = template_1080p
        self._template_720p = template_720p

        self._detector = RoomIdDetector(config.to_detection_config())

        self.is_running = False
        self.is_monitoring = False
        self.has_connected = False
        self._lamp_state: Tuple[bool, bool] = (False, False)
        self._profiler = PipelineProfiler()

    async def _sleep_while_running(self, seconds: float) -> None:
        """`stop_worker` 後も長い `sleep` で待たされないよう、短い区切りで `asyncio.sleep` する。"""
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        deadline = time.perf_counter() + seconds
        while self.is_running:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                break
            await asyncio.sleep(min(_SLEEP_SLICE_SEC, remaining))

    def _emit_detection_lamps(self, room: bool, id_ok: bool) -> None:
        state = (room, id_ok)
        if state != self._lamp_state:
            self._lamp_state = state
            self._on_detection_lamps(room, id_ok)

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.is_running = True
        try:
            loop.run_until_complete(self._async_main())
        finally:
            self.is_running = False
            loop.close()

    def stop_worker(self) -> None:
        self.is_running = False
        self.is_monitoring = False

    async def _apply_confirmed_id(self, confirmed_id: str, prev_copied: str) -> None:
        """確定 ID のクリップボード反映・検出器更新・GUI/拡張連携コールバック（SSE はコピー成否に依存しない）。"""
        if prev_copied and prev_copied != confirmed_id:
            await try_remove_text_from_clipboard_history(prev_copied)
        copy_ok = False
        try:
            pyperclip.copy(confirmed_id)
            copy_ok = True
        except Exception:
            logger.warning(
                "クリップボードへのコピーに失敗しました（GUI はコピー成功として更新しません）",
                exc_info=True,
            )
        if copy_ok:
            self._detector.acknowledge_copy(confirmed_id)
            self.on_id_found(confirmed_id)
        if self._on_confirmed_id_bridge:
            self._on_confirmed_id_bridge(confirmed_id)

    async def _async_main(self) -> None:
        obs_config = self.config.to_obs_connection_config()

        processor = ImageProcessor(
            template_1080p_path=self._template_1080p,
            template_720p_path=self._template_720p,
            debug=False,
        )
        engine = WinRTOcrEngine()

        poll_fast = self._detector.poll_fast

        try:
            async with OBSCapture(obs_config) as cap:
                self.on_status("OBSに接続しました。ソース一覧を取得中...")
                sources = await cap.get_source_list()
                self.has_connected = True
                self.on_sources(sources)

                while self.is_running:
                    if not self.is_monitoring or not self.config.target_source:
                        self._emit_detection_lamps(False, False)
                        # 監視オフ中に溜まった pending を捨て、再開時に誤確定しないようにする
                        self._detector.reset_pending_only()
                        await self._sleep_while_running(0.5)
                        continue

                    self._profiler.reset_frame()
                    t_cap = time.perf_counter()
                    frame = await cap.get_source_screenshot(
                        self.config.target_source,
                        width=self.config.screenshot_width,
                        height=self.config.screenshot_height,
                        image_format=self.config.screenshot_format,
                        quality=self.config.screenshot_quality,
                    )
                    self._profiler.add_phase("capture", t_cap)

                    if frame is None:
                        if not cap.is_connected:
                            self._emit_detection_lamps(False, False)
                            self.on_status("OBS との接続が切れました。再接続してください。")
                            self.on_disconnected()
                            break
                        self._emit_detection_lamps(False, False)
                        await self._sleep_while_running(poll_fast)
                        self._profiler.end_frame()
                        continue

                    t_roi = time.perf_counter()
                    # OpenCV・テンプレ照合は同期処理が重いのでスレッドプールへ退避し、
                    # 同一ループ上の OBS WebSocket 応答性を少しでも確保する。
                    roi = await asyncio.to_thread(processor.find_and_extract_roi, frame)
                    self._profiler.add_phase("roi", t_roi)

                    if roi is not None:
                        t_ocr = time.perf_counter()
                        raw_text = await engine.recognize(roi)
                        self._profiler.add_phase("ocr", t_ocr)
                        room_id = await asyncio.to_thread(
                            processor.extract_room_id_from_text, raw_text
                        )
                        self._emit_detection_lamps(True, room_id is not None)
                        prev_copied = self._detector.state.last_copied_id
                        result = self._detector.process(room_id)

                        if result.confirmed_id:
                            await self._apply_confirmed_id(result.confirmed_id, prev_copied)
                        self._profiler.end_frame()
                        await self._sleep_while_running(result.poll_interval)
                    else:
                        self._emit_detection_lamps(False, False)
                        self._detector.reset_pending_only()
                        self._profiler.end_frame()
                        await self._sleep_while_running(poll_fast)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("OCR ワーカーで未処理例外")
            self._emit_detection_lamps(False, False)
            self.on_status(f"エラー: {e}")
            self.on_disconnected()
            self.has_connected = False
            self.is_monitoring = False

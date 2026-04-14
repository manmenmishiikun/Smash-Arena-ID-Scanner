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


class OCRWorker(threading.Thread):
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
    ):
        super().__init__(daemon=True)
        self.config = config
        self.on_status = on_status
        self.on_sources = on_sources
        self.on_id_found = on_id_found
        self.on_disconnected = on_disconnected
        self._on_detection_lamps = on_detection_lamps or (lambda _r, _i: None)
        self._template_1080p = template_1080p
        self._template_720p = template_720p

        self._detector = RoomIdDetector()

        self.is_running = False
        self.is_monitoring = False
        self.has_connected = False
        self._lamp_state: Tuple[bool, bool] = (False, False)
        self._profiler = PipelineProfiler()

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
            loop.close()

    def stop_worker(self) -> None:
        self.is_running = False
        self.is_monitoring = False

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
                        await asyncio.sleep(0.5)
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
                        await asyncio.sleep(poll_fast)
                        self._profiler.end_frame()
                        continue

                    t_roi = time.perf_counter()
                    roi = processor.find_and_extract_roi(frame)
                    self._profiler.add_phase("roi", t_roi)

                    if roi is not None:
                        t_ocr = time.perf_counter()
                        raw_text = await engine.recognize(roi)
                        self._profiler.add_phase("ocr", t_ocr)
                        room_id = processor.extract_room_id_from_text(raw_text)
                        self._emit_detection_lamps(True, room_id is not None)
                        prev_copied = self._detector.state.last_copied_id
                        result = self._detector.process(room_id)

                        if result.confirmed_id:
                            if prev_copied and prev_copied != result.confirmed_id:
                                await try_remove_text_from_clipboard_history(prev_copied)
                            pyperclip.copy(result.confirmed_id)
                            self.on_id_found(result.confirmed_id)
                        self._profiler.end_frame()
                        await asyncio.sleep(result.poll_interval)
                    else:
                        self._emit_detection_lamps(False, False)
                        self._detector.reset_pending_only()
                        self._profiler.end_frame()
                        await asyncio.sleep(poll_fast)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("OCR ワーカーで未処理例外")
            self._emit_detection_lamps(False, False)
            self.on_status(f"エラー: {e}")
            self.on_disconnected()
            self.has_connected = False
            self.is_monitoring = False

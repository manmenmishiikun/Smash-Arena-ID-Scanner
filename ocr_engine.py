"""
ocr_engine.py
OCR処理モジュール（WinRT OCR実装）

将来のMac対応等で別エンジンに差し替える場合は、同じ `recognize(image_bgr)` 契約を
満たすクラスに差し替えればよい。
"""

import cv2
import numpy as np


class WinRTOcrEngine:
    """Windows.Media.Ocr を使った OCRエンジン。外部ツール不要。"""

    def __init__(self, language: str = "en-US"):
        """
        Args:
            language: OCR言語タグ (例: "en-US")。英語を最優先にする。
        """
        self._language_tag = language
        self._engine = None  # 初回 recognize() 時に初期化

    def _build_engine(self):
        """OcrEngineを遅延初期化して返す。"""
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.globalization import Language

        lang = Language(self._language_tag)
        if OcrEngine.is_language_supported(lang):
            return OcrEngine.try_create_from_language(lang)
        return OcrEngine.try_create_from_user_profile_languages()

    @staticmethod
    def _to_software_bitmap(image_bgra: np.ndarray):
        """BGR→BGRA変換済みのndarrayをSoftwareBitmapに変換して返す。"""
        from winsdk.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode
        from winsdk.windows.storage.streams import DataWriter

        height, width, _ = image_bgra.shape
        raw_bytes = image_bgra.tobytes()

        writer = DataWriter()
        try:
            try:
                writer.write_bytes(raw_bytes)
            except Exception:
                writer.write_bytes(list(raw_bytes))
            buffer = writer.detach_buffer()
        finally:
            try:
                writer.close()
            except Exception:
                pass

        return SoftwareBitmap.create_copy_from_buffer(
            buffer,
            BitmapPixelFormat.BGRA8,
            width,
            height,
            BitmapAlphaMode.PREMULTIPLIED,
        )

    async def recognize(self, image_bgr: np.ndarray) -> str:
        """
        前処理済みBGR画像をOCRにかけ、生テキストを返す。
        前処理（二値化等）は呼び出し側の ImageProcessor に委譲する。
        """
        if self._engine is None:
            self._engine = self._build_engine()

        image_bgra = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2BGRA)
        # WinRT バッファへ渡す前に連続領域化（不要なコピーを避けつつ互換性を確保）
        image_bgra = np.ascontiguousarray(image_bgra)
        software_bitmap = self._to_software_bitmap(image_bgra)

        result = await self._engine.recognize_async(software_bitmap)
        return result.text.strip()

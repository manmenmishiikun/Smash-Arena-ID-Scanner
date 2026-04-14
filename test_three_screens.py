"""
test_screen_正解_誤読.png 形式の3枚で OCR パイプラインを検証する。
"""
import asyncio
import os
import re
import sys

import cv2

from image_processor import ImageProcessor
from ocr_engine import WinRTOcrEngine

TEMPLATE = os.path.join(os.path.dirname(__file__), "arenahere.png")

# 追加の画像置き場（デフォルトはこのスクリプトと同じディレクトリ＝リポジトリ直下）
_here = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ASSETS_DIR = _here


def _parse_expected(path: str) -> tuple[str, str] | None:
    base = os.path.basename(path)
    # ..._test_screen_0RKHM_QRKHM.png
    m = re.search(r"test_screen_([A-Za-z0-9]{5})_([A-Za-z0-9]{5})\.png$", base)
    if m:
        return m.group(1).upper(), m.group(2).upper()
    return None


async def run_one(
    processor: ImageProcessor, engine: WinRTOcrEngine, image_path: str
) -> None:
    exp = _parse_expected(image_path)
    frame = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if frame is None:
        print(f"  [SKIP] 読み込めません: {image_path}")
        return
    roi = processor.find_and_extract_roi(frame)
    if roi is None:
        print(f"  [FAIL] テンプレ不一致: {os.path.basename(image_path)}")
        return
    raw = await engine.recognize(roi)
    rid = processor.extract_room_id_from_text(raw)
    name = os.path.basename(image_path)
    print(f"  ファイル: {name}")
    print(f"  OCR raw: {raw!r}")
    print(f"  抽出ID:   {rid!r}")
    if exp:
        ok, bad = exp
        match = "OK" if rid == ok else "NG"
        print(f"  正解ID:   {ok}  （以前の誤読: {bad}）")
        print(f"  正解一致: {match}")
    print()


async def main() -> None:
    assets_dir = os.environ.get("SMASH_TEST_ASSETS", DEFAULT_ASSETS_DIR)
    if len(sys.argv) > 1:
        assets_dir = sys.argv[1]
    short_names = [
        "test_screen_0RKHM_QRKHM.png",
        "test_screen_J6KHC_JGKHC.png",
        "test_screen_J909W_J9Q9W.png",
    ]
    paths = []
    here = _here
    for short in short_names:
        p_local = os.path.join(here, short)
        p_assets = os.path.join(assets_dir, short)
        if os.path.isfile(p_local):
            paths.append(p_local)
        elif os.path.isfile(p_assets):
            paths.append(p_assets)
        else:
            print(f"[WARN] 見つかりません: {short}", file=sys.stderr)

    if not paths:
        print("画像ファイルが見つかりません。assets パスを確認してください。")
        return

    if not os.path.isfile(TEMPLATE):
        print(f"arenahere.png がありません: {TEMPLATE}")
        return

    processor = ImageProcessor(TEMPLATE)
    engine = WinRTOcrEngine()

    print("=" * 60)
    print("  test_screen 3枚 OCR テスト")
    print("=" * 60)
    for p in paths:
        await run_one(processor, engine, p)


if __name__ == "__main__":
    asyncio.run(main())

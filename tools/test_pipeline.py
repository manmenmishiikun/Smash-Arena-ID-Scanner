"""
test_pipeline.py
統合テストスクリプト

このスクリプトは以下の2つのテストを選択して実行できます。

  [1] ローカル画像テスト
      test_screen.png を読み込み、テンプレートマッチング → 前処理 → OCR の全工程を検証する。
      → OBS が起動していなくてもテスト可能。

  [2] OBS WebSocket 接続テスト
      実際に OBS に接続し、指定ソースからライブ画像を取得して OCR を実行する。
      → OBS WebSocket v5 が有効な状態で実行する。

使い方:
  $ python tools/test_pipeline.py          # メニューが表示される
  $ python tools/test_pipeline.py --local  # [1] のみ実行
  $ python tools/test_pipeline.py --obs    # [2] のみ実行
"""

import asyncio
import sys
import os
import cv2

# ── リポジトリ直下のモジュールをインポート
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TOOLS_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from image_processor import ImageProcessor
from ocr_engine import WinRTOcrEngine
from obs_capture import OBSCapture, ObsConnectionConfig

TEMPLATE_PATH = os.path.join(ROOT_DIR, "assets", "templates", "arenahere.png")
TEST_SCREEN_PATH = os.path.join(ROOT_DIR, "assets", "samples", "test_screen.png")


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

async def run_ocr_on_frame(frame, processor: ImageProcessor, engine: WinRTOcrEngine, label: str = ""):
    """1フレームに対してOCR全工程を実行するヘルパー関数。"""
    print(f"\n{'-'*40}")
    if label:
        print(f"  frame: {label}")

    roi = processor.find_and_extract_roi(frame)
    if roi is None:
        print("  [FAIL] template matching failed")
        return None

    print("  [OK] icon detected")

    raw_text = await engine.recognize(roi)
    print(f"  OCR raw: '{raw_text}'")

    room_id = processor.extract_room_id_from_text(raw_text)
    if room_id:
        print(f"  [SUCCESS] Room ID: {room_id}")
    else:
        print(f"  [FAIL] room ID not found")

    return room_id


# ---------------------------------------------------------------------------
# テスト [1]: ローカル画像テスト
# ---------------------------------------------------------------------------

async def test_local_image():
    print("\n" + "="*50)
    print("  [1] ローカル画像テスト")
    print("="*50)

    if not os.path.exists(TEST_SCREEN_PATH):
        print(f"✗ '{TEST_SCREEN_PATH}' が見つかりません。")
        print("  ヒント: テスト用のゲーム画面スクショを 'assets/samples/test_screen.png' に保存してください。")
        return

    processor = ImageProcessor(TEMPLATE_PATH, debug=True)
    engine = WinRTOcrEngine()

    frame = cv2.imread(TEST_SCREEN_PATH, cv2.IMREAD_COLOR)
    if frame is None:
        print("✗ 画像の読み込みに失敗しました。")
        return

    await run_ocr_on_frame(frame, processor, engine, label="assets/samples/test_screen.png")

    print("\n  デバッグ画像を保存しました:")
    for fname in ["debug_1_roi_original.png", "debug_2_binary.png",
                  "debug_3_morphed.png", "debug_4_inverted.png"]:
        path = os.path.join(ROOT_DIR, fname)
        if os.path.exists(path):
            print(f"    - {fname}")


# ---------------------------------------------------------------------------
# テスト [2]: OBS WebSocket 接続テスト
# ---------------------------------------------------------------------------

async def test_obs_connection():
    print("\n" + "="*50)
    print("  [2] OBS WebSocket 接続テスト")
    print("="*50)

    # 接続情報を入力（後でGUIに置き換え）
    host = input("  OBS の IP アドレス [localhost]: ").strip() or "localhost"
    port_str = input("  OBS WebSocket ポート番号 [4455]: ").strip() or "4455"
    password = input("  OBS WebSocket パスワード（なければ空白でEnter）: ").strip()

    config = ObsConnectionConfig(host=host, port=int(port_str), password=password)

    async with OBSCapture(config) as cap:
        print("\n  ソース一覧を取得中...")
        sources = await cap.get_source_list()

        if not sources:
            print("  ✗ シーンにソースが見つかりませんでした。")
            return

        print("  利用可能なソース:")
        for i, s in enumerate(sources):
            print(f"    [{i}] {s}")

        idx_str = input("  OCRに使うソースの番号を入力: ").strip()
        try:
            source_name = sources[int(idx_str)]
        except (ValueError, IndexError):
            print("  ✗ 無効な番号です。")
            return

        print(f"\n  '{source_name}' からスクリーンショットを取得中...")
        frame = await cap.get_source_screenshot(source_name)

        if frame is None:
            print("  ✗ スクリーンショットの取得に失敗しました。")
            return

        processor = ImageProcessor(TEMPLATE_PATH, debug=True)
        engine = WinRTOcrEngine()

        await run_ocr_on_frame(frame, processor, engine, label=source_name)


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

async def main():
    print("スマブラSP 部屋ID OCR テスト")

    args = sys.argv[1:]

    if "--local" in args:
        await test_local_image()
    elif "--obs" in args:
        await test_obs_connection()
    else:
        print("\nどちらのテストを実行しますか？")
        print("  [1] ローカル画像テスト (assets/samples/test_screen.png を使用)")
        print("  [2] OBS WebSocket 接続テスト")
        choice = input("番号を入力 (1/2): ").strip()

        if choice == "1":
            await test_local_image()
        elif choice == "2":
            await test_obs_connection()
        else:
            print("キャンセルしました。")


if __name__ == "__main__":
    asyncio.run(main())

"""
8枚の固定サンプル画像で OCR 精度を検証する回帰テスト。

ファイル名規約:
  test_screen_<EXPECTED>_<OLD_OCR>.png
例:
  test_screen_J909W_J9Q9W.png
  -> 正解は J909W、過去誤読は J9Q9W
"""

import asyncio
import os
import re
from dataclasses import dataclass

import cv2

from image_processor import ImageProcessor
from ocr_engine import WinRTOcrEngine


ROOT = os.path.dirname(__file__)
TEMPLATE_1080 = os.path.join(ROOT, "arenahere.png")
TEMPLATE_720 = os.path.join(ROOT, "arenahere_720p.png")

SAMPLES = [
    "test_screen_0RKHM_QRKHM.png",
    "test_screen_6CMCN_CantRead.png",
    "test_screen_6XHGT_6XH6T.png",
    "test_screen_317GK_3176K.png",
    "test_screen_J6KHC_JGKHC.png",
    "test_screen_J909W_J9Q9W.png",
    "test_screen_KQJJN_K0JJN.png",
    "test_screen.png",
]

NAME_PATTERN = re.compile(
    r"^test_screen_(?P<expected>[A-Za-z0-9]{5})_(?P<old>[A-Za-z0-9]{5}|CantRead)\.png$"
)


@dataclass
class OneResult:
    name: str
    expected: str | None
    old_ocr: str | None
    raw: str
    extracted: str | None
    matched: bool
    roi_found: bool


def parse_expected(filename: str) -> tuple[str | None, str | None]:
    m = NAME_PATTERN.match(filename)
    if not m:
        return None, None
    return m.group("expected").upper(), m.group("old")


async def run_one(
    processor: ImageProcessor,
    engine: WinRTOcrEngine,
    image_name: str,
) -> OneResult:
    path = os.path.join(ROOT, image_name)
    expected, old_ocr = parse_expected(image_name)

    frame = cv2.imread(path, cv2.IMREAD_COLOR)
    if frame is None:
        return OneResult(
            name=image_name,
            expected=expected,
            old_ocr=old_ocr,
            raw="",
            extracted=None,
            matched=False,
            roi_found=False,
        )

    roi = processor.find_and_extract_roi(frame)
    if roi is None:
        return OneResult(
            name=image_name,
            expected=expected,
            old_ocr=old_ocr,
            raw="",
            extracted=None,
            matched=False,
            roi_found=False,
        )

    raw = await engine.recognize(roi)
    extracted = processor.extract_room_id_from_text(raw)
    matched = bool(expected and extracted == expected)
    return OneResult(
        name=image_name,
        expected=expected,
        old_ocr=old_ocr,
        raw=raw,
        extracted=extracted,
        matched=matched,
        roi_found=True,
    )


async def main() -> None:
    processor = ImageProcessor(
        TEMPLATE_1080, TEMPLATE_720 if os.path.isfile(TEMPLATE_720) else None
    )
    engine = WinRTOcrEngine()

    print("=" * 72)
    print("OCR サンプル回帰テスト (8 images)")
    print("=" * 72)

    results = []
    for name in SAMPLES:
        r = await run_one(processor, engine, name)
        results.append(r)

        print(f"\n[FILE] {r.name}")
        if r.expected:
            print(f"  expected: {r.expected}   old_ocr: {r.old_ocr}")
        print(f"  roi_found: {r.roi_found}")
        print(f"  raw_text:  {r.raw!r}")
        print(f"  extracted: {r.extracted!r}")
        if r.expected:
            print(f"  result:    {'OK' if r.matched else 'NG'}")

    checked = [x for x in results if x.expected]
    ok = sum(1 for x in checked if x.matched)
    total = len(checked)
    print("\n" + "-" * 72)
    print(f"TOTAL: {ok}/{total}")
    if ok != total:
        ngs = [x.name for x in checked if not x.matched]
        print("NG files:")
        for n in ngs:
            print(f"  - {n}")


if __name__ == "__main__":
    asyncio.run(main())

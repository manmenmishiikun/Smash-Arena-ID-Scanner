"""システムトレイ用アイコン画像の生成。"""

import os

from PIL import Image, ImageDraw

_TRAY_SIZE = 64


def create_tray_image(base_path: str) -> Image.Image:
    """`icons/arena scan@128.png` があればそれを用い、なければ従来のプレースホルダを描画する。"""
    path = os.path.join(base_path, "icons", "arena scan@128.png")
    if os.path.isfile(path):
        img = Image.open(path).convert("RGBA")
        if img.size != (_TRAY_SIZE, _TRAY_SIZE):
            img = img.resize((_TRAY_SIZE, _TRAY_SIZE), Image.Resampling.LANCZOS)
        return img

    img = Image.new("RGBA", (_TRAY_SIZE, _TRAY_SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, _TRAY_SIZE - 2, _TRAY_SIZE - 2], fill=(50, 130, 220, 255))
    d.text((12, 18), "SA", fill="white")
    return img

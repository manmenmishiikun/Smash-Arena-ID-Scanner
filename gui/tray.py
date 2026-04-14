"""システムトレイ用アイコン画像の生成。"""

from PIL import Image, ImageDraw


def create_tray_image() -> Image.Image:
    """シンプルなシステムトレイアイコン画像を生成する。"""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, size - 2, size - 2], fill=(50, 130, 220, 255))
    d.text((12, 18), "SA", fill="white")
    return img

"""
リポジトリ `icons/` の mate flow 128px 素材から、Chrome 拡張用の複数解像度 PNG を生成する。
128px をソースにダウンスケールする（巨大な原本 PNG はパッケージに含めない）。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC_GREEN = ROOT / "icons" / "mate flow-green@128.png"
SRC_RED = ROOT / "icons" / "mate flow-red@128.png"
OUT_DIR = ROOT / "chrome-extension" / "icons"


def _resize(src: Path, size: int) -> Image.Image:
    im = Image.open(src).convert("RGBA")
    return im.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    if not SRC_GREEN.is_file() or not SRC_RED.is_file():
        raise SystemExit(f"Missing source icons: {SRC_GREEN} / {SRC_RED}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ストア・拡張管理画面用（manifest `icons`）: 緑のセット
    _resize(SRC_GREEN, 16).save(OUT_DIR / "icon16.png")
    _resize(SRC_GREEN, 48).save(OUT_DIR / "icon48.png")
    _resize(SRC_GREEN, 128).save(OUT_DIR / "icon128.png")

    # ツールバー切替用（action + setIcon）: 16 / 32 / 48
    for w in (16, 32, 48):
        _resize(SRC_GREEN, w).save(OUT_DIR / f"action-green-{w}.png")
        _resize(SRC_RED, w).save(OUT_DIR / f"action-red-{w}.png")

    print(f"Wrote extension icons under {OUT_DIR}")


if __name__ == "__main__":
    main()

"""画像処理のテキスト抽出・曖昧展開の回帰テスト（テンプレ画像は最小生成）。"""

import numpy as np
import cv2
import pytest

from image_processor import MAX_O_BRANCH_POSITIONS, ImageProcessor


def _make_minimal_processor(tmp_path) -> ImageProcessor:
    """テンプレートとして読める最小画像を生成。"""
    p = tmp_path / "tpl.png"
    gray = np.zeros((50, 80), dtype=np.uint8)
    cv2.imwrite(str(p), gray)
    return ImageProcessor(str(p))


def test_pick_room_id_by_text_order_leftmost() -> None:
    s = "XXXXX J909W extra KQJJN"
    candidates = {"J909W", "KQJJN"}
    picked = ImageProcessor._pick_room_id_by_text_order(s, candidates)
    assert picked == "J909W"


def test_expand_o_variants_caps_branch_count() -> None:
    many_o = "O" * (MAX_O_BRANCH_POSITIONS + 4)
    variants = ImageProcessor._expand_o_variants(many_o)
    assert len(variants) == 2**MAX_O_BRANCH_POSITIONS


def test_extract_room_id_direct_single(tmp_path) -> None:
    proc = _make_minimal_processor(tmp_path)
    # 先頭に別の5桁候補が並ばないよう、ID のみ
    assert proc.extract_room_id_from_text("  J909W  ") == "J909W"


def test_room_id_pattern_five_chars() -> None:
    from image_processor import ROOM_ID_PATTERN

    assert ROOM_ID_PATTERN.search("ABCDE")
    assert ROOM_ID_PATTERN.search("J909W")
    assert not ROOM_ID_PATTERN.search("O")  # O は有効文字セット外

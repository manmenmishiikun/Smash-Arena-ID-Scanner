"""OBS ペイロードデコードの単体テスト（ネットワークなし）。"""

import numpy as np
import cv2

from obs_capture import decode_screenshot_payload


def test_decode_screenshot_payload_valid_png_base64() -> None:
    img = np.zeros((10, 20, 3), dtype=np.uint8)
    img[:, :] = (40, 80, 120)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    import base64

    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    raw = f"data:image/png;base64,{b64}"
    out = decode_screenshot_payload(raw)
    assert out is not None
    assert out.shape[:2] == (10, 20)


def test_decode_screenshot_payload_invalid_base64() -> None:
    assert decode_screenshot_payload("data:image/jpeg;base64,!!!") is None


def test_decode_screenshot_payload_empty() -> None:
    assert decode_screenshot_payload("") is None

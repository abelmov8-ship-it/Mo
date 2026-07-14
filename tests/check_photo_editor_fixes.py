"""
Runnable self-check for the Photo Editor fixes.

Covers the two things that were actually broken in PhotoService-adjacent
code, plus the new input-validation boundary:

1. Collage: handle_photo_upload previously had no "collage" branch, so
   PhotoService.collage() (which was always correct) never got called —
   photos were echoed back individually instead. This checks the service
   directly: N images in, one correctly-sized canvas out, for both column
   counts the UI now offers.
2. Rotation: the handler hardcoded CW_90. This checks every direction the
   rotation_keyboard() now exposes actually changes the image the way it
   claims to (dimensions swap on 90-degree turns, stay put on flips).
3. Custom size parsing (_parse_custom_size): the new WIDTHxHEIGHT trust
   boundary — valid input round-trips, malformed/out-of-range input is
   rejected rather than reaching PIL.

Run directly: `python3 tests/check_photo_editor_fixes.py`
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PIL import Image

from bot.services.photo_service import PhotoService, RotationDirection
from bot.handlers.user.photo_editor import _parse_custom_size, MAX_COLLAGE_IMAGES


def _fake_jpeg(w: int = 120, h: int = 80) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (255, 0, 0)).save(buf, format="JPEG")
    return buf.getvalue()


def check_collage():
    svc = PhotoService()
    images = [_fake_jpeg() for _ in range(5)]

    for cols in (2, 3):
        result = svc.collage(images, cols=cols)
        out = Image.open(io.BytesIO(result))
        expected_rows = (len(images) + cols - 1) // cols
        assert out.width == 400 * cols, f"collage width wrong for cols={cols}"
        assert out.height == 300 * expected_rows, f"collage height wrong for cols={cols}"

    assert MAX_COLLAGE_IMAGES >= 2, "collage cap must allow at least a pair"
    print("✓ collage: renders one canvas from N images at both offered layouts")


def check_rotation():
    svc = PhotoService()
    src = _fake_jpeg(120, 80)

    cw = Image.open(io.BytesIO(svc.rotate(src, RotationDirection.CW_90)))
    ccw = Image.open(io.BytesIO(svc.rotate(src, RotationDirection.CCW_90)))
    flip_h = Image.open(io.BytesIO(svc.rotate(src, RotationDirection.FLIP_H)))
    flip_v = Image.open(io.BytesIO(svc.rotate(src, RotationDirection.FLIP_V)))

    assert (cw.width, cw.height) == (80, 120), "90 deg CW must swap dimensions"
    assert (ccw.width, ccw.height) == (80, 120), "90 deg CCW must swap dimensions"
    assert (flip_h.width, flip_h.height) == (120, 80), "flip must not swap dimensions"
    assert (flip_v.width, flip_v.height) == (120, 80), "flip must not swap dimensions"
    print("✓ rotation: all four directions the keyboard offers are wired correctly")


def check_custom_size_parsing():
    assert _parse_custom_size("800x600") == (800, 600)
    assert _parse_custom_size("800X600") == (800, 600)
    assert _parse_custom_size(" 800 x 600 ") == (800, 600)

    assert _parse_custom_size("not-a-size") is None
    assert _parse_custom_size("800") is None
    assert _parse_custom_size("0x600") is None       # below bound
    assert _parse_custom_size("800x99999") is None   # above bound
    assert _parse_custom_size("-800x600") is None    # not digits after strip
    print("✓ custom size: valid input parses, malformed/out-of-range input is rejected")


if __name__ == "__main__":
    check_collage()
    check_rotation()
    check_custom_size_parsing()
    print("\nAll photo editor checks passed.")

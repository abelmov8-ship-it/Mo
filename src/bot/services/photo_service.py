from __future__ import annotations

import io
from enum import Enum

from PIL import Image, ImageDraw, ImageFont


class RotationDirection(str, Enum):
    CW_90 = "cw90"
    CCW_90 = "ccw90"
    FLIP_H = "flip_h"
    FLIP_V = "flip_v"


class PhotoService:
    """
    All operations accept raw image bytes and return processed raw bytes (JPEG).
    This keeps the service stateless and easy to test.
    """

    @staticmethod
    def _open(data: bytes) -> Image.Image:
        return Image.open(io.BytesIO(data)).convert("RGB")

    @staticmethod
    def _to_bytes(img: Image.Image, quality: int = 90) -> bytes:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        buf.seek(0)
        return buf.read()

    def resize(self, data: bytes, width: int, height: int) -> bytes:
        img = self._open(data)
        img = img.resize((width, height), Image.LANCZOS)
        return self._to_bytes(img)

    def rotate(self, data: bytes, direction: RotationDirection) -> bytes:
        img = self._open(data)
        match direction:
            case RotationDirection.CW_90:
                img = img.rotate(-90, expand=True)
            case RotationDirection.CCW_90:
                img = img.rotate(90, expand=True)
            case RotationDirection.FLIP_H:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            case RotationDirection.FLIP_V:
                img = img.transpose(Image.FLIP_TOP_BOTTOM)
        return self._to_bytes(img)

    def add_text(
        self,
        data: bytes,
        text: str,
        position: tuple[int, int] = (10, 10),
        font_size: int = 36,
        color: tuple[int, int, int] = (255, 255, 255),
    ) -> bytes:
        img = self._open(data)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

        # Drop shadow for readability
        shadow_offset = (2, 2)
        draw.text(
            (position[0] + shadow_offset[0], position[1] + shadow_offset[1]),
            text, fill=(0, 0, 0), font=font,
        )
        draw.text(position, text, fill=color, font=font)
        return self._to_bytes(img)

    def add_frame(self, data: bytes, border_px: int = 20, color: tuple[int, int, int] = (0, 0, 0)) -> bytes:
        img = self._open(data)
        new_w = img.width + border_px * 2
        new_h = img.height + border_px * 2
        framed = Image.new("RGB", (new_w, new_h), color)
        framed.paste(img, (border_px, border_px))
        return self._to_bytes(framed)

    def collage(self, images_data: list[bytes], cols: int = 2) -> bytes:
        """Creates a grid collage. All images are resized to a common thumbnail size."""
        thumb_w, thumb_h = 400, 300
        images = [self._open(d).resize((thumb_w, thumb_h), Image.LANCZOS) for d in images_data]

        rows = (len(images) + cols - 1) // cols
        canvas = Image.new("RGB", (thumb_w * cols, thumb_h * rows), (20, 20, 20))

        for idx, img in enumerate(images):
            row, col = divmod(idx, cols)
            canvas.paste(img, (col * thumb_w, row * thumb_h))

        return self._to_bytes(canvas, quality=85)

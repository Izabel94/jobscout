import base64
from io import BytesIO

from PIL import Image

from jobscout.ui.settings import cv_photo_b64


def _decode(b64: str) -> Image.Image:
    return Image.open(BytesIO(base64.b64decode(b64)))


def test_large_png_becomes_jpeg_within_600x800() -> None:
    buf = BytesIO()
    Image.new("RGBA", (2176, 2956), (10, 20, 30, 255)).save(buf, "PNG")
    out = _decode(cv_photo_b64(buf.getvalue()))
    assert out.format == "JPEG"
    assert out.width <= 600 and out.height <= 800
    assert abs(out.width / out.height - 2176 / 2956) < 0.01


def test_small_photo_is_not_upscaled() -> None:
    buf = BytesIO()
    Image.new("RGB", (300, 400), "white").save(buf, "JPEG")
    assert _decode(cv_photo_b64(buf.getvalue())).size == (300, 400)

"""PDF rendering tests — skipped if WeasyPrint's native deps (pango/glib) are missing."""

from pathlib import Path
from unittest.mock import patch

import pytest

try:
    from jobscout.cv_render import _photo_data_uri, _split_header, cv_markdown_to_pdf

    _WEASYPRINT_OK = True
    _SKIP_REASON = ""
except (ImportError, OSError) as e:  # pragma: no cover - import-time native dep check
    _WEASYPRINT_OK = False
    _SKIP_REASON = f"weasyprint native deps missing — run `brew install pango glib` ({e})"


@pytest.mark.skipif(not _WEASYPRINT_OK, reason=_SKIP_REASON)
def test_renders_pdf(tmp_path: Path) -> None:
    md_text = "# Izabel\n\nizabel@example.com\n\n## Experience\n- AI engineer at OMR\n"
    out = cv_markdown_to_pdf(md_text, tmp_path / "cv.pdf")
    assert out.exists()
    assert out.stat().st_size > 1000


@pytest.mark.skipif(not _WEASYPRINT_OK, reason=_SKIP_REASON)
def test_split_header_extracts_h1_and_contact() -> None:
    html = "<h1>Izabel</h1>\n<p>izabel@example.com</p>\n<h2>Summary</h2>\n<p>body</p>"
    header, body = _split_header(html)
    assert "<h1>Izabel</h1>" in header
    assert "izabel@example.com" in header
    assert "<h2>Summary</h2>" in body
    assert "<h1>" not in body


@pytest.mark.skipif(not _WEASYPRINT_OK, reason=_SKIP_REASON)
def test_split_header_falls_back_when_pattern_missing() -> None:
    html = "<h2>No name heading</h2><p>body</p>"
    header, body = _split_header(html)
    assert header == ""
    assert body == html


@pytest.mark.skipif(not _WEASYPRINT_OK, reason=_SKIP_REASON)
def test_photo_data_uri_returns_none_when_file_absent(tmp_path: Path) -> None:
    with patch("jobscout.cv_render.load_profile", return_value={"photo_path": str(tmp_path / "nope.jpg")}):
        assert _photo_data_uri() is None


@pytest.mark.skipif(not _WEASYPRINT_OK, reason=_SKIP_REASON)
def test_photo_data_uri_encodes_existing_file(tmp_path: Path) -> None:
    fake_photo = tmp_path / "headshot.jpg"
    fake_photo.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")
    with patch("jobscout.cv_render.load_profile", return_value={"photo_path": str(fake_photo)}):
        uri = _photo_data_uri()
    assert uri is not None
    assert uri.startswith("data:image/jpeg;base64,")

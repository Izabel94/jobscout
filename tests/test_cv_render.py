import base64
from unittest.mock import MagicMock

import pytest

from jobscout.cv_render import cv_markdown_to_pdf, cv_markdown_to_pdf_bytes


@pytest.fixture(autouse=True)
def _no_photo(monkeypatch):
    monkeypatch.setattr("jobscout.cv_render.load_profile", lambda: {})


def _profile_with_photo(monkeypatch, jpeg: bytes) -> None:
    b64 = base64.b64encode(jpeg).decode("ascii")
    monkeypatch.setattr("jobscout.cv_render.load_profile", lambda: {"photo_jpeg_b64": b64})


def test_cv_markdown_to_pdf_calls_set_content_and_pdf(tmp_path):
    page = MagicMock()
    out = tmp_path / "cv.pdf"

    result = cv_markdown_to_pdf(
        "# Julian Engelke\n\nHamburg\n\n### Mediaplus | Hamburg\n**Senior Consultant** | *2023-now*",
        out,
        page=page,
    )

    assert result == out
    assert page.set_content.called
    html_arg = page.set_content.call_args.args[0]
    assert "<h1>Julian Engelke</h1>" in html_arg
    # Header-meta split applied to "Company | Location"
    assert 'class="header-title"' in html_arg
    assert 'class="header-meta"' in html_arg

    page.pdf.assert_called_once()
    pdf_kwargs = page.pdf.call_args.kwargs
    assert pdf_kwargs.get("format") == "A4"
    assert pdf_kwargs.get("print_background") is True
    assert pdf_kwargs.get("path") == str(out)


def test_cv_markdown_to_pdf_renders_without_photo_when_profile_has_none(tmp_path):
    page = MagicMock()
    cv_markdown_to_pdf("# Test\n\nbody", tmp_path / "cv.pdf", page=page)
    html_arg = page.set_content.call_args.args[0]
    # template should still render — photo just absent
    assert "<h1>Test</h1>" in html_arg


def test_cv_markdown_to_pdf_embeds_photo_from_profile(tmp_path, monkeypatch):
    _profile_with_photo(monkeypatch, b"\xff\xd8\xff\xe0fake-jpeg-bytes")
    page = MagicMock()
    cv_markdown_to_pdf("# Test", tmp_path / "cv.pdf", page=page)
    html_arg = page.set_content.call_args.args[0]
    assert "data:image/jpeg;base64," in html_arg


def test_cv_pdf_bytes_embeds_profile_photo(monkeypatch):
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (60, 80), "red").save(buf, "JPEG")
    without = cv_markdown_to_pdf_bytes("# Test\n\nbody")
    _profile_with_photo(monkeypatch, buf.getvalue())
    with_photo = cv_markdown_to_pdf_bytes("# Test\n\nbody")
    assert b"/Subtype /Image" in with_photo
    assert b"/Subtype /Image" not in without

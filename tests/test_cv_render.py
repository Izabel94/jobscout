from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jobscout.cv_render import cv_markdown_to_pdf


def test_cv_markdown_to_pdf_calls_set_content_and_pdf(tmp_path):
    page = MagicMock()
    out = tmp_path / "cv.pdf"

    result = cv_markdown_to_pdf(
        "# Julian Engelke\n\nHamburg\n\n### Mediaplus | Hamburg\n**Senior Consultant** | *2023–now*",
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


def test_cv_markdown_to_pdf_renders_without_photo_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("jobscout.cv_render._PHOTO_PATH", tmp_path / "nope.jpg")
    page = MagicMock()
    cv_markdown_to_pdf("# Test\n\nbody", tmp_path / "cv.pdf", page=page)
    html_arg = page.set_content.call_args.args[0]
    # template should still render — photo just absent
    assert "<h1>Test</h1>" in html_arg


def test_cv_markdown_to_pdf_embeds_photo_data_uri_when_file_present(tmp_path, monkeypatch):
    photo = tmp_path / "profile_photo.jpg"
    photo.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")
    monkeypatch.setattr("jobscout.cv_render._PHOTO_PATH", photo)
    page = MagicMock()
    cv_markdown_to_pdf("# Test", tmp_path / "cv.pdf", page=page)
    html_arg = page.set_content.call_args.args[0]
    assert "data:image/jpeg;base64," in html_arg

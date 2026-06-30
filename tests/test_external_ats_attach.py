from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from jobscout.apply.external_ats import _apply_action


def _page_with_locator() -> tuple[MagicMock, MagicMock]:
    loc = MagicMock()
    loc.count.return_value = 1
    page = MagicMock()
    page.locator.return_value.first = loc
    return page, loc


def test_attach_cover_letter_pdf_uploads_file(tmp_path: Path) -> None:
    cl = tmp_path / "anschreiben.pdf"
    cl.write_bytes(b"%PDF-1.4 fake")
    page, loc = _page_with_locator()
    ok, note = _apply_action(
        page,
        {"selector": "#cl", "action": "attach", "value": "cover_letter_pdf"},
        cv_pdf_path=None,
        cover_letter="…",
        cover_letter_pdf_path=cl,
    )
    assert ok is True
    loc.set_input_files.assert_called_once_with(str(cl))


def test_attach_cover_letter_pdf_skips_when_missing(tmp_path: Path) -> None:
    page, loc = _page_with_locator()
    ok, note = _apply_action(
        page,
        {"selector": "#cl", "action": "attach", "value": "cover_letter_pdf"},
        cv_pdf_path=None,
        cover_letter="…",
        cover_letter_pdf_path=tmp_path / "nope.pdf",
    )
    assert ok is False
    assert "cover_letter_pdf missing" in note
    loc.set_input_files.assert_not_called()


def test_attach_cv_pdf_still_works(tmp_path: Path) -> None:
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4 fake")
    page, loc = _page_with_locator()
    ok, note = _apply_action(
        page,
        {"selector": "#cv", "action": "attach", "value": "cv_pdf"},
        cv_pdf_path=cv,
        cover_letter="…",
    )
    assert ok is True
    loc.set_input_files.assert_called_once_with(str(cv))

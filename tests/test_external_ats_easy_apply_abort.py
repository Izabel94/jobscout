from unittest.mock import MagicMock

import pytest

from jobscout.apply.external_ats import (
    _EASY_APPLY_SUBMIT_RE,
    EasyApplyAfterClickError,
    _assert_not_easy_apply,
)


def _fake_page(url: str, modal_open: bool = False) -> MagicMock:
    """Fake page: `modal_open` is what the Easy-Apply modal probe returns."""
    page = MagicMock()
    page.url = url
    page.evaluate.return_value = modal_open
    return page


def test_assert_not_easy_apply_passes_for_external_ats_url():
    _assert_not_easy_apply(_fake_page("https://boards.greenhouse.io/acme/jobs/12345"))


def test_assert_not_easy_apply_raises_when_modal_open_on_linkedin():
    with pytest.raises(EasyApplyAfterClickError):
        _assert_not_easy_apply(
            _fake_page("https://www.linkedin.com/jobs/easyApply/4123456789/", modal_open=True)
        )


def test_assert_not_easy_apply_raises_for_sdui_apply_overlay():
    # The newer SDUI apply flow keeps /jobs/view/<id>/apply — the modal probe
    # returns True for that pathname even before the dialog renders.
    with pytest.raises(EasyApplyAfterClickError):
        _assert_not_easy_apply(
            _fake_page(
                "https://www.linkedin.com/jobs/view/4427370199/apply/?openSDUIApplyFlow=true",
                modal_open=True,
            )
        )


def test_assert_not_easy_apply_passes_on_linkedin_without_modal():
    # Still on linkedin.com with NO modal is a sign-in gate blocking an offsite
    # job (e.g. 'Auf Firmenwebseite bewerben' behind login) — NOT Easy Apply.
    # The caller flags it login_wall instead; raising here would permanently
    # mislabel the listing's apply_method.
    _assert_not_easy_apply(
        _fake_page("https://www.linkedin.com/jobs/view/4427370199/?trackingId=EX8", modal_open=False)
    )


def test_easy_apply_submit_label_detection():
    # The driver must stop (never click) on these; advance on the rest.
    for label in ("submit application", "Bewerbung absenden", "absenden"):
        assert _EASY_APPLY_SUBMIT_RE.search(label)
    for label in ("continue to next step", "next", "weiter", "review your application", "review"):
        assert not _EASY_APPLY_SUBMIT_RE.search(label)

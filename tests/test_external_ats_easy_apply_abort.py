from unittest.mock import MagicMock

import pytest

from jobscout.apply.external_ats import (
    _EASY_APPLY_SUBMIT_RE,
    EasyApplyAfterClickError,
    _assert_not_easy_apply,
)


def _fake_page(url: str) -> MagicMock:
    page = MagicMock()
    page.url = url
    return page


def test_assert_not_easy_apply_passes_for_external_ats_url():
    _assert_not_easy_apply(_fake_page("https://boards.greenhouse.io/acme/jobs/12345"))


def test_assert_not_easy_apply_raises_for_easy_apply_path():
    with pytest.raises(EasyApplyAfterClickError):
        _assert_not_easy_apply(
            _fake_page("https://www.linkedin.com/jobs/easyApply/4123456789/")
        )


def test_assert_not_easy_apply_raises_for_case_and_query_variants():
    with pytest.raises(EasyApplyAfterClickError):
        _assert_not_easy_apply(
            _fake_page("https://www.LINKEDIN.com/jobs/easyApply/4123456789/?refId=abc")
        )


def test_assert_not_easy_apply_raises_for_sdui_apply_overlay():
    # The newer SDUI apply flow keeps the /jobs/view/<id>/ URL — caught by host.
    with pytest.raises(EasyApplyAfterClickError):
        _assert_not_easy_apply(
            _fake_page("https://www.linkedin.com/jobs/view/4427370199/?trackingId=EX8")
        )


def test_assert_not_easy_apply_raises_for_any_linkedin_form_page():
    with pytest.raises(EasyApplyAfterClickError):
        _assert_not_easy_apply(
            _fake_page("https://www.linkedin.com/jobs/view/4427370199/apply/?openSDUIApplyFlow=true")
        )


def test_easy_apply_submit_label_detection():
    # The driver must stop (never click) on these; advance on the rest.
    for label in ("submit application", "Bewerbung absenden", "absenden"):
        assert _EASY_APPLY_SUBMIT_RE.search(label)
    for label in ("continue to next step", "next", "weiter", "review your application", "review"):
        assert not _EASY_APPLY_SUBMIT_RE.search(label)

from unittest.mock import MagicMock

import pytest

from jobscout.apply.external_ats import (
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

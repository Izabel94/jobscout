"""_await_user_submit: records a submission on a real click OR a confirmation
page, and never phantom-submits on close/timeout."""

from __future__ import annotations

from unittest.mock import patch

from jobscout.apply.external_ats import ApplyOutcome, _await_user_submit


class _FakePage:
    """URL advances one step per loop (via the patched sleep); optionally
    reports closed once its index reaches `closed_at`."""

    def __init__(self, urls: list[str], closed_at: int | None = None) -> None:
        self._urls = urls
        self.i = 0
        self._closed_at = closed_at

    @property
    def url(self) -> str:
        return self._urls[min(self.i, len(self._urls) - 1)]

    def is_closed(self) -> bool:
        return self._closed_at is not None and self.i >= self._closed_at


def _advance(page: _FakePage):
    def _sleep(_seconds: float) -> None:
        page.i += 1

    return _sleep


def test_click_records_submission():
    page = _FakePage(["u"])
    res = _await_user_submit(page, {"clicked": True}, max_wait_seconds=10)
    assert res.outcome == ApplyOutcome.SUBMITTED


def test_confirmation_page_records_submission_even_without_click():
    page = _FakePage(["form", "form", "confirmation"])
    with (
        patch("jobscout.apply.external_ats.time.sleep", side_effect=_advance(page)),
        patch("jobscout.apply.external_ats._reached_confirmation", return_value=True),
    ):
        res = _await_user_submit(page, {"clicked": False}, max_wait_seconds=30)
    assert res.outcome == ApplyOutcome.SUBMITTED


def test_navigation_that_is_not_confirmation_then_close_is_attempted():
    page = _FakePage(["form", "elsewhere", "elsewhere"], closed_at=2)
    with (
        patch("jobscout.apply.external_ats.time.sleep", side_effect=_advance(page)),
        patch("jobscout.apply.external_ats._reached_confirmation", return_value=False),
    ):
        res = _await_user_submit(page, {"clicked": False}, max_wait_seconds=30)
    assert res.outcome == ApplyOutcome.FILLED_NO_SUBMIT


def test_timeout_without_action_is_attempted():
    page = _FakePage(["form"])
    res = _await_user_submit(page, {"clicked": False}, max_wait_seconds=0)
    assert res.outcome == ApplyOutcome.FILLED_NO_SUBMIT

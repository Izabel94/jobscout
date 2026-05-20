"""Tests for jobscout.apply.worker dispatch logic."""

from pathlib import Path
from unittest.mock import patch


def test_process_one_dispatches_upwork():
    row = {"id": "req-1", "listing_id": "list-1", "source": "upwork"}
    listing = {
        "id": "list-1", "url": "https://upwork.com/jobs/~abc",
        "title": "Test", "description": "desc",
    }
    draft = {"id": "draft-1", "body": "proposal text", "adapted_cv": "# CV"}

    with (
        patch("jobscout.apply.worker._fetch_listing", return_value=listing),
        patch("jobscout.apply.worker._fetch_latest_draft", return_value=draft),
        patch("jobscout.apply.worker._render_cv_pdf", return_value=Path("/tmp/cv.pdf")),
        patch("jobscout.apply.upwork.apply") as upwork_apply,
        patch("jobscout.apply.worker.mark_apply_request_done") as mark_done,
    ):
        from jobscout.apply.worker import process_one

        process_one(row)

        upwork_apply.assert_called_once()
        mark_done.assert_called_once_with("req-1", executed_draft_id="draft-1", notes=None)


def test_process_one_dispatches_external_ats_for_bundesagentur():
    row = {"id": "req-2", "listing_id": "list-2", "source": "bundesagentur"}
    listing = {
        "id": "list-2", "url": "https://arbeitsagentur.de/...",
        "title": "AI", "description": "desc",
        "raw": {"externeUrl": "https://employer.example/apply"},
    }
    draft = {"id": "draft-2", "body": "proposal", "adapted_cv": "# CV"}

    with (
        patch("jobscout.apply.worker._fetch_listing", return_value=listing),
        patch("jobscout.apply.worker._fetch_latest_draft", return_value=draft),
        patch("jobscout.apply.worker._render_cv_pdf", return_value=Path("/tmp/cv.pdf")),
        patch("jobscout.apply.external_ats.apply") as ext_apply,
        patch("jobscout.apply.worker.mark_apply_request_done"),
    ):
        from jobscout.apply.worker import process_one

        process_one(row)

        ext_apply.assert_called_once()
        kwargs = ext_apply.call_args.kwargs
        assert kwargs["ats_url"] == "https://employer.example/apply"


def test_process_one_dispatches_external_ats_for_linkedin_using_listing_url_when_no_externeurl():
    row = {"id": "req-3", "listing_id": "list-3", "source": "linkedin"}
    listing = {
        "id": "list-3", "url": "https://linkedin.com/jobs/view/123",
        "title": "AI", "description": "desc", "raw": {},
    }
    draft = {"id": "draft-3", "body": "proposal", "adapted_cv": "# CV"}

    with (
        patch("jobscout.apply.worker._fetch_listing", return_value=listing),
        patch("jobscout.apply.worker._fetch_latest_draft", return_value=draft),
        patch("jobscout.apply.worker._render_cv_pdf", return_value=Path("/tmp/cv.pdf")),
        patch("jobscout.apply.external_ats.apply") as ext_apply,
        patch("jobscout.apply.worker.mark_apply_request_done"),
    ):
        from jobscout.apply.worker import process_one

        process_one(row)

        kwargs = ext_apply.call_args.kwargs
        assert kwargs["ats_url"] == "https://linkedin.com/jobs/view/123"


def test_process_one_marks_failed_on_exception():
    row = {"id": "req-4", "listing_id": "list-4", "source": "upwork"}

    with (
        patch("jobscout.apply.worker._fetch_listing", side_effect=RuntimeError("boom")),
        patch("jobscout.apply.worker.mark_apply_request_failed") as mark_failed,
    ):
        from jobscout.apply.worker import process_one

        process_one(row)

        mark_failed.assert_called_once()
        assert "boom" in mark_failed.call_args.kwargs["error"]


def test_process_one_marks_failed_on_unknown_source():
    row = {"id": "req-5", "listing_id": "list-5", "source": "mystery"}
    listing = {"id": "list-5", "url": "x", "title": "t", "description": "d"}
    draft = {"id": "d", "body": "p", "adapted_cv": "# CV"}

    with (
        patch("jobscout.apply.worker._fetch_listing", return_value=listing),
        patch("jobscout.apply.worker._fetch_latest_draft", return_value=draft),
        patch("jobscout.apply.worker._render_cv_pdf", return_value=Path("/tmp/cv.pdf")),
        patch("jobscout.apply.worker.mark_apply_request_failed") as mark_failed,
    ):
        from jobscout.apply.worker import process_one

        process_one(row)

        mark_failed.assert_called_once()
        assert "mystery" in mark_failed.call_args.kwargs["error"]


def test_process_one_dispatches_freelancermap():
    row = {"id": "req-fm", "listing_id": "list-fm", "source": "freelancermap"}
    listing = {
        "id": "list-fm",
        "url": "https://freelancermap.de/projekt/abc",
        "title": "RAG project",
        "description": "desc",
    }
    draft = {"id": "draft-fm", "body": "proposal", "adapted_cv": "# CV"}

    with (
        patch("jobscout.apply.worker._fetch_listing", return_value=listing),
        patch("jobscout.apply.worker._fetch_latest_draft", return_value=draft),
        patch("jobscout.apply.worker._render_cv_pdf", return_value=Path("/tmp/cv.pdf")),
        patch("jobscout.apply.freelancermap.apply") as fm_apply,
        patch("jobscout.apply.worker.mark_apply_request_done"),
    ):
        from jobscout.apply.worker import process_one

        process_one(row)

        fm_apply.assert_called_once_with(
            "https://freelancermap.de/projekt/abc",
            "proposal",
            Path("/tmp/cv.pdf"),
        )

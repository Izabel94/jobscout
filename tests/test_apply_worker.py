from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def fake_external_apply(monkeypatch):
    """Replace external_ats.apply with a spy."""
    calls = []
    fake = MagicMock(side_effect=lambda **kw: calls.append(kw))
    monkeypatch.setattr("jobscout.apply.external_ats.apply", fake)
    return calls, fake


@pytest.fixture
def fake_render_cv(monkeypatch, tmp_path):
    """Replace cv_render.cv_markdown_to_pdf with a no-op that produces a file."""
    def _render(cv_md, out, *, page=None):
        out.write_bytes(b"%PDF-1.4 stub")
        return out
    monkeypatch.setattr("jobscout.apply.worker._render_cv_pdf", lambda md_, **kw: tmp_path / "cv.pdf")
    (tmp_path / "cv.pdf").write_bytes(b"%PDF-1.4 stub")
    return tmp_path / "cv.pdf"


def test_process_one_dispatches_external_apply_listing(fake_external_apply, fake_render_cv, monkeypatch):
    from jobscout.apply import worker

    listing = {
        "id": "listing-1",
        "title": "Senior Performance Marketing",
        "description": "Lead programmatic at AdTechCo",
        "url": "https://www.linkedin.com/jobs/view/4123456789/",
        "company_url_direct": "https://boards.greenhouse.io/adtechco/jobs/123",
        "apply_method": "external_apply",
        "source": "linkedin",
    }
    draft = {"id": "draft-1", "body": "Dear hiring team…", "adapted_cv": "# Julian\n\n…"}

    monkeypatch.setattr(worker, "_fetch_listing", lambda _: listing)
    monkeypatch.setattr(worker, "_fetch_latest_draft", lambda _: draft)
    record_calls: list[tuple] = []
    monkeypatch.setattr(
        worker,
        "_record_submission_and_mark_done",
        lambda req_id, listing_id, draft_id: record_calls.append((req_id, listing_id, draft_id)),
    )
    monkeypatch.setattr(worker, "_open_render_tab", lambda: MagicMock())

    row = {"id": "req-1", "listing_id": "listing-1", "source": "linkedin"}
    worker.process_one(row)

    calls, _ = fake_external_apply
    assert len(calls) == 1
    kw = calls[0]
    assert kw["ats_url"] == "https://boards.greenhouse.io/adtechco/jobs/123"
    assert kw["proposal"] == "Dear hiring team…"
    assert kw["listing_title"] == "Senior Performance Marketing"
    assert record_calls == [("req-1", "listing-1", "draft-1")]


def test_process_one_falls_back_to_listing_url_when_no_company_url_direct(
    fake_external_apply, fake_render_cv, monkeypatch
):
    from jobscout.apply import worker

    listing = {
        "id": "listing-1",
        "title": "X",
        "description": "Y",
        "url": "https://example.com/apply",
        "company_url_direct": None,
        "apply_method": "external_apply",
        "source": "indeed",
    }
    draft = {"id": "draft-1", "body": "…", "adapted_cv": "…"}
    monkeypatch.setattr(worker, "_fetch_listing", lambda _: listing)
    monkeypatch.setattr(worker, "_fetch_latest_draft", lambda _: draft)
    monkeypatch.setattr(worker, "_record_submission_and_mark_done", lambda *a: None)
    monkeypatch.setattr(worker, "_open_render_tab", lambda: MagicMock())

    worker.process_one({"id": "req", "listing_id": "listing-1", "source": "indeed"})

    calls, _ = fake_external_apply
    assert calls[0]["ats_url"] == "https://example.com/apply"

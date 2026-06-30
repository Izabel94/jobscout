from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_external_apply(monkeypatch):
    """Replace external_ats.apply with a spy that reports a confirmed submit."""
    from jobscout.apply.external_ats import ApplyOutcome, ApplyResult

    calls = []

    def _fake(**kw):
        calls.append(kw)
        return ApplyResult(ApplyOutcome.SUBMITTED)

    fake = MagicMock(side_effect=_fake)
    monkeypatch.setattr("jobscout.apply.external_ats.apply", fake)
    return calls, fake


@pytest.fixture
def fake_render_cv(monkeypatch, tmp_path):
    """Replace cv_render.cv_markdown_to_pdf with a no-op that produces a file."""
    def _render(cv_md, out, *, page=None):
        out.write_bytes(b"%PDF-1.4 stub")
        return out
    monkeypatch.setattr("jobscout.apply.worker._render_cv_pdf", lambda md_, **kw: tmp_path / "cv.pdf")
    monkeypatch.setattr("jobscout.apply.worker._render_cover_letter_pdf", lambda md_, **kw: tmp_path / "cl.pdf")
    (tmp_path / "cv.pdf").write_bytes(b"%PDF-1.4 stub")
    (tmp_path / "cl.pdf").write_bytes(b"%PDF-1.4 stub")
    return tmp_path / "cv.pdf"


def test_process_one_dispatches_external_apply_listing(fake_external_apply, fake_render_cv, monkeypatch):
    from jobscout.apply import worker

    listing = {
        "id": "listing-1",
        "title": "Senior Performance Marketing",
        "description": "Lead programmatic at AdTechCo",
        "url": "https://www.linkedin.com/jobs/view/4123456789/",
        "raw": {
            "job_url_direct": "https://boards.greenhouse.io/adtechco/jobs/123",
            "company_url_direct": "https://adtechco.example",
        },
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


def test_process_one_prefers_job_url_direct_over_company_url_direct(
    fake_external_apply, fake_render_cv, monkeypatch
):
    """raw.job_url_direct is the specific apply URL; raw.company_url_direct is the
    company careers homepage (often useless). Worker must prefer the specific URL."""
    from jobscout.apply import worker

    listing = {
        "id": "listing-1",
        "title": "X",
        "description": "Y",
        "url": "https://de.indeed.com/viewjob?jk=abc",
        "raw": {
            "job_url_direct": "https://jobdb.softgarden.de/job/64822241",
            "company_url_direct": "https://www.donner-reuschel.de",
        },
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
    assert calls[0]["ats_url"] == "https://jobdb.softgarden.de/job/64822241"


def test_process_one_falls_back_to_listing_url_when_no_raw_signals(
    fake_external_apply, fake_render_cv, monkeypatch
):
    from jobscout.apply import worker

    listing = {
        "id": "listing-1",
        "title": "X",
        "description": "Y",
        "url": "https://example.com/apply",
        "raw": {},
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


def test_process_one_rejects_easy_apply_listing(monkeypatch):
    from jobscout.apply import worker

    listing = {
        "id": "l1", "title": "T", "description": "D", "url": "https://x",
        "company_url_direct": None, "apply_method": "easy_apply", "source": "linkedin",
    }
    monkeypatch.setattr(worker, "_fetch_listing", lambda _: listing)
    monkeypatch.setattr(worker, "_fetch_latest_draft", lambda _: {"id": "d", "body": "", "adapted_cv": ""})
    failed: list[tuple[str, str]] = []
    monkeypatch.setattr(worker, "mark_apply_request_failed",
                        lambda rid, *, error, notes=None: failed.append((rid, error)))
    fired = []
    monkeypatch.setattr("jobscout.apply.external_ats.apply",
                        lambda **kw: fired.append(kw))

    worker.process_one({"id": "r1", "listing_id": "l1", "source": "linkedin"})

    assert fired == []
    assert failed == [("r1", "easy_apply_after_claim")]


def test_process_one_flips_apply_method_on_easy_apply_after_click(monkeypatch):
    from jobscout.apply import external_ats, worker

    listing = {
        "id": "l1", "title": "T", "description": "D", "url": "https://x",
        "company_url_direct": "https://x", "apply_method": "external_apply", "source": "linkedin",
    }
    monkeypatch.setattr(worker, "_fetch_listing", lambda _: listing)
    monkeypatch.setattr(worker, "_fetch_latest_draft",
                        lambda _: {"id": "d", "body": "b", "adapted_cv": "c"})
    monkeypatch.setattr(worker, "_render_cv_pdf", lambda *a, **kw: Path("/tmp/cv.pdf"))
    monkeypatch.setattr(worker, "_render_cover_letter_pdf", lambda *a, **kw: Path("/tmp/cl.pdf"))

    def _raise(**_kw):
        raise external_ats.EasyApplyAfterClickError("landed on /jobs/easyApply/")
    monkeypatch.setattr("jobscout.apply.external_ats.apply", _raise)

    flips: list[str] = []
    monkeypatch.setattr(worker, "_flip_listing_to_easy_apply",
                        lambda listing_id: flips.append(listing_id))
    failed: list[tuple[str, str]] = []
    monkeypatch.setattr(worker, "mark_apply_request_failed",
                        lambda rid, *, error, notes=None: failed.append((rid, error)))

    worker.process_one({"id": "r1", "listing_id": "l1", "source": "linkedin"})

    assert flips == ["l1"]
    assert failed == [("r1", "easy_apply_detected_at_click")]


def _listing(**over):
    base = {
        "id": "l1", "title": "T", "description": "D", "url": "https://x",
        "raw": {"job_url_direct": "https://ats.example/job/1"},
        "apply_method": "external_apply", "source": "linkedin",
    }
    base.update(over)
    return base


def _wire_outcome(monkeypatch, outcome_result):
    """Drive process_one with a stubbed apply() returning outcome_result, and
    spy on every terminal DB transition. Returns the spy dict."""
    from jobscout.apply import worker

    monkeypatch.setattr(worker, "_fetch_listing", lambda _: _listing())
    monkeypatch.setattr(worker, "_fetch_latest_draft",
                        lambda _: {"id": "draft-1", "body": "b", "adapted_cv": "c"})
    monkeypatch.setattr(worker, "_render_cv_pdf", lambda *a, **kw: Path("/tmp/cv.pdf"))
    monkeypatch.setattr(worker, "_render_cover_letter_pdf", lambda *a, **kw: Path("/tmp/cl.pdf"))
    monkeypatch.setattr("jobscout.apply.external_ats.apply", lambda **kw: outcome_result)

    spy: dict[str, object] = {}
    monkeypatch.setattr(worker, "_record_submission_and_mark_done",
                        lambda rid, lid, did: spy.setdefault("submission", (rid, lid, did)))
    monkeypatch.setattr(worker, "mark_apply_request_attempted",
                        lambda rid, *, executed_draft_id, notes=None: spy.setdefault("attempted", (rid, executed_draft_id)))
    monkeypatch.setattr(worker, "mark_apply_request_manual_required",
                        lambda rid, *, reason, notes=None: spy.setdefault("manual_required", (rid, reason)))
    monkeypatch.setattr(worker, "set_listing_apply_block_reason",
                        lambda lid, reason: spy.setdefault("block_reason", (lid, reason)))
    monkeypatch.setattr(worker, "mark_apply_request_failed",
                        lambda rid, *, error, notes=None: spy.setdefault("failed", (rid, error)))

    worker.process_one({"id": "req-1", "listing_id": "l1", "source": "linkedin"})
    return spy


def test_submitted_outcome_records_submission(monkeypatch):
    from jobscout.apply.external_ats import ApplyOutcome, ApplyResult

    spy = _wire_outcome(monkeypatch, ApplyResult(ApplyOutcome.SUBMITTED))
    assert spy.get("submission") == ("req-1", "l1", "draft-1")
    assert "attempted" not in spy and "manual_required" not in spy


def test_filled_no_submit_does_not_record_submission(monkeypatch):
    """The phantom-submission guard: a filled-but-not-submitted form must NOT
    record a submission — it's marked 'attempted', nothing more."""
    from jobscout.apply.external_ats import ApplyOutcome, ApplyResult

    spy = _wire_outcome(monkeypatch, ApplyResult(ApplyOutcome.FILLED_NO_SUBMIT))
    assert "submission" not in spy
    assert spy.get("attempted") == ("req-1", "draft-1")


def test_not_fillable_flags_listing_for_manual(monkeypatch):
    """A login wall / 0-field page flags the listing (apply_block_reason) and
    marks the request manual_required — never a submission, never a retry."""
    from jobscout.apply.external_ats import ApplyOutcome, ApplyResult

    spy = _wire_outcome(monkeypatch, ApplyResult(ApplyOutcome.NOT_FILLABLE, reason="login_wall"))
    assert "submission" not in spy
    assert spy.get("block_reason") == ("l1", "login_wall")
    assert spy.get("manual_required") == ("req-1", "login_wall")


@pytest.mark.parametrize("over", [{"status": "rejected"}, {"apply_block_reason": "login_wall"}])
def test_process_one_skips_rejected_or_blocked_listing(monkeypatch, over):
    """A request queued before a filter pass must not apply once its listing was
    rejected (agency/dupe) or flagged unfillable."""
    from jobscout.apply import worker

    monkeypatch.setattr(worker, "_fetch_listing", lambda _id: _listing(**over))
    fired: list = []
    monkeypatch.setattr("jobscout.apply.external_ats.apply", lambda **kw: fired.append(kw))
    failed: list = []
    monkeypatch.setattr(worker, "mark_apply_request_failed",
                        lambda rid, *, error, notes=None: failed.append((rid, error)))

    worker.process_one({"id": "r1", "listing_id": "l1", "source": "linkedin"})

    assert fired == []
    assert failed == [("r1", "listing_no_longer_eligible")]


def test_main_loop_stops_at_daily_cap(monkeypatch):
    from jobscout.apply import worker

    submissions_count = [8]
    monkeypatch.setattr(worker, "count_submissions_today_external", lambda: submissions_count[0])
    monkeypatch.setattr(worker, "recover_stale_apply_claims", lambda: 0)

    pending_rows = [
        {"id": "r1", "listing_id": "l1", "source": "linkedin"},
        {"id": "r2", "listing_id": "l2", "source": "linkedin"},
        {"id": "r3", "listing_id": "l3", "source": "linkedin"},
    ]
    claims: list[str] = []

    def _claim():
        if pending_rows:
            row = pending_rows.pop(0)
            claims.append(row["id"])
            return row
        return None
    monkeypatch.setattr(worker, "claim_one_pending_apply_request", _claim)

    def _process(_row):
        submissions_count[0] += 1  # simulate a successful submission
    monkeypatch.setattr(worker, "process_one", _process)

    worker.main()

    # Should stop after 2 (8 → 9 → 10), leaving r3 pending. The 3rd claim happens
    # but we re-check cap immediately and stop without processing.
    assert claims == ["r1", "r2"]


def test_main_loop_skips_if_already_capped(monkeypatch):
    from jobscout.apply import worker

    monkeypatch.setattr(worker, "count_submissions_today_external", lambda: 10)
    monkeypatch.setattr(worker, "recover_stale_apply_claims", lambda: 0)
    claims: list[str] = []
    monkeypatch.setattr(worker, "claim_one_pending_apply_request",
                        lambda: claims.append("called") or None)
    monkeypatch.setattr(worker, "process_one", lambda _: None)

    worker.main()

    assert claims == []  # never even attempted a claim

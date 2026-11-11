"""Apply-queue worker — claims pending apply_requests rows, renders the CV
and cover letter PDFs, and dispatches to external_ats. EXTERNAL_APPLY
only; LinkedIn Easy Apply is surfaced for manual click and never reaches here.

Invoked by macOS launchd via scripts/apply-worker-local.sh every 5 min.
Windows .bat + Task Scheduler equivalents land in Phase 5.
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

from jobscout.db import (
    claim_one_pending_apply_request,
    count_submissions_today_external,
    get_latest_draft_for_listing,
    get_listing_by_id,
    mark_apply_request_attempted,
    mark_apply_request_done,
    mark_apply_request_failed,
    mark_apply_request_manual_required,
    record_submission,
    recover_stale_apply_claims,
    set_listing_apply_block_reason,
)

log = logging.getLogger("apply-worker")


def _fetch_listing(listing_id: str) -> dict[str, Any] | None:
    return get_listing_by_id(listing_id)


def _fetch_latest_draft(listing_id: str) -> dict[str, Any] | None:
    return get_latest_draft_for_listing(listing_id)


def _ats_url_for(listing: dict[str, Any]) -> str:
    """Resolve the URL the apply worker should attach to.

    JobSpy populates two related signals inside `listings.raw` (JSONB), NOT as
    top-level columns:
      - `raw.job_url_direct`  — the specific job's apply URL (Softgarden,
        Greenhouse, Lever, ICIMS, Recruitee, etc.). This is what we want.
      - `raw.company_url_direct` — the company's careers homepage. Usually
        useless for a single apply (lands on a search page).

    Reading from the top level (the old behaviour) always returned None,
    causing every Indeed external_apply listing to fall back to
    listing.url — the Indeed wrapper, whose only Apply CTA is
    `<button id="indeedApplyButton">Mit Indeed bewerben</button>` (no href,
    opens an in-page modal external_ats can't drive).

    Resolution order:
      1. raw.job_url_direct  — preferred, deep link into the ATS form
      2. raw.company_url_direct  — fallback, careers homepage
      3. listing.url  — last resort (Indeed/LinkedIn wrapper)
    """
    raw = listing.get("raw") or {}
    return str(raw.get("job_url_direct") or raw.get("company_url_direct") or listing["url"])


def _render_cv_pdf(cv_markdown: str) -> Path:
    """Write the adapted CV PDF as `lebenslauf|cv-<name>-<date>.pdf`, so the recipient sees the
    candidate's name on the attachment. A fresh temp dir per apply keeps queued applies
    from overwriting each other."""
    from jobscout.cv_render import cv_markdown_to_pdf_bytes, pdf_filename

    out = Path(tempfile.mkdtemp(prefix="jobscout-")) / pdf_filename("cv", cv_markdown)
    out.write_bytes(cv_markdown_to_pdf_bytes(cv_markdown))
    return out


def _render_cover_letter_pdf(cover_letter: str) -> Path:
    """Write the cover letter PDF, for forms that want it as a file upload."""
    from jobscout.cv_render import cover_letter_to_pdf_bytes, pdf_filename

    out = Path(tempfile.mkdtemp(prefix="jobscout-")) / pdf_filename("cover-letter", cover_letter)
    out.write_bytes(cover_letter_to_pdf_bytes(cover_letter))
    return out


def _record_submission_and_mark_done(request_id: str, listing_id: str, draft_id: str) -> None:
    record_submission(listing_id, draft_id, channel="external_apply", notes=None)
    mark_apply_request_done(request_id, executed_draft_id=draft_id, notes=None)


def _handle_outcome(request_id: str, listing_id: str, draft_id: str, result: Any) -> None:
    """Map an external_ats ApplyResult to a DB transition. Only a confirmed
    submit click records a submission — the rest never do."""
    from jobscout.apply.external_ats import ApplyOutcome

    if result.outcome == ApplyOutcome.SUBMITTED:
        _record_submission_and_mark_done(request_id, listing_id, draft_id)
    elif result.outcome == ApplyOutcome.NOT_FILLABLE:
        reason = result.reason or "not_fillable"
        set_listing_apply_block_reason(listing_id, reason)
        mark_apply_request_manual_required(request_id, reason=reason)
    else:  # FILLED_NO_SUBMIT — filled but the user didn't submit (or not yet)
        mark_apply_request_attempted(request_id, executed_draft_id=draft_id)


def _flip_listing_to_easy_apply(listing_id: str) -> None:
    """Promote a misclassified EXTERNAL_APPLY listing to EASY_APPLY so the UI
    surfaces it under the manual section next time."""
    from jobscout.db import _client

    _client().table("listings").update({"apply_method": "easy_apply"}).eq("id", listing_id).execute()


def process_one(row: dict[str, Any]) -> None:
    request_id = row["id"]
    try:
        listing = _fetch_listing(row["listing_id"])
        if listing is None:
            raise RuntimeError(f"listing {row['listing_id']} not found")
        # A request queued before a later filter pass can outlive its listing:
        # if the listing was since rejected (agency/dupe), expired (freshness
        # sweep or removed in the UI), or flagged unfillable, don't apply —
        # drop the stale request.
        if listing.get("status") in ("rejected", "expired") or listing.get("apply_block_reason"):
            mark_apply_request_failed(request_id, error="listing_no_longer_eligible", notes=None)
            return
        if listing.get("apply_method") != "external_apply":
            mark_apply_request_failed(request_id, error="easy_apply_after_claim", notes=None)
            return

        draft = _fetch_latest_draft(row["listing_id"])
        if draft is None:
            raise RuntimeError(f"no draft for listing {row['listing_id']}")

        cv_pdf_path = _render_cv_pdf(draft["adapted_cv"])
        cover_letter_pdf_path = _render_cover_letter_pdf(draft["body"])

        from jobscout.apply import external_ats

        try:
            result = external_ats.apply(
                ats_url=_ats_url_for(listing),
                proposal=draft["body"],
                cv_pdf_path=cv_pdf_path,
                listing_title=listing.get("title") or "",
                listing_description=listing.get("description") or "",
                adapted_cv_md=draft["adapted_cv"],
                cover_letter_pdf_path=cover_letter_pdf_path,
            )
        except external_ats.EasyApplyAfterClickError:
            _flip_listing_to_easy_apply(listing["id"])
            mark_apply_request_failed(request_id, error="easy_apply_detected_at_click", notes=None)
            return

        _handle_outcome(request_id, listing["id"], draft["id"], result)
    except Exception as e:
        log.exception("apply request %s failed", request_id)
        mark_apply_request_failed(request_id, error=str(e), notes=None)


_DAILY_CAP = 10


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    recovered = recover_stale_apply_claims()
    if recovered:
        log.info("recovered %d stale claim(s)", recovered)
    processed = 0
    while True:
        already_today = count_submissions_today_external()
        if already_today >= _DAILY_CAP:
            log.info("daily cap reached (%d/%d) — exiting", already_today, _DAILY_CAP)
            break
        row = claim_one_pending_apply_request()
        if row is None:
            break
        log.info(
            "processing apply_request %s (source=%s, %d/%d applied today)",
            row["id"],
            row["source"],
            already_today,
            _DAILY_CAP,
        )
        process_one(row)
        processed += 1
    log.info("worker done — processed %d request(s)", processed)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Apply-queue worker — claims pending apply_requests rows, renders the CV
PDF in the CDP-attached Chrome, and dispatches to external_ats. EXTERNAL_APPLY
only; LinkedIn Easy Apply is surfaced for manual click and never reaches here.

Invoked by macOS launchd via scripts/apply-worker-local.sh every 5 min.
Windows .bat + Task Scheduler equivalents land in Phase 5.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jobscout.db import (
    claim_one_pending_apply_request,
    get_latest_draft_for_listing,
    get_listing_by_id,
    mark_apply_request_done,
    mark_apply_request_failed,
    record_submission,
    recover_stale_apply_claims,
)

log = logging.getLogger("apply-worker")


def _fetch_listing(listing_id: str) -> dict[str, Any] | None:
    return get_listing_by_id(listing_id)


def _fetch_latest_draft(listing_id: str) -> dict[str, Any] | None:
    return get_latest_draft_for_listing(listing_id)


def _ats_url_for(listing: dict[str, Any]) -> str:
    """Greenhouse / Lever / Workable / employer direct URL parsed by derive.py
    lives in `company_url_direct`. Fall back to the listing URL if absent
    (e.g. Indeed listings where derive marked it EXTERNAL_APPLY based on a
    different signal)."""
    return str(listing.get("company_url_direct") or listing["url"])


def _open_render_tab():
    """Open a throwaway tab on the CDP Chrome for cv_render to call page.pdf() on."""
    from playwright.sync_api import sync_playwright as _spw

    cdp_url = os.environ["JOBSCOUT_CDP_URL"]
    p = _spw().start()
    browser = p.chromium.connect_over_cdp(cdp_url)
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()
    page._jobscout_pw = p  # type: ignore[attr-defined]
    page._jobscout_browser = browser  # type: ignore[attr-defined]
    return page


def _close_render_tab(page) -> None:
    import contextlib

    with contextlib.suppress(Exception):
        page.close()
    with contextlib.suppress(Exception):
        page._jobscout_browser.close()  # type: ignore[attr-defined]
    with contextlib.suppress(Exception):
        page._jobscout_pw.stop()  # type: ignore[attr-defined]


def _render_cv_pdf(cv_markdown: str, **_kwargs: object) -> Path:
    """Render the adapted CV markdown to a PDF in temp dir, return its path."""
    from jobscout.cv_render import cv_markdown_to_pdf

    stamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    out = Path(tempfile.gettempdir()) / f"jobscout-cv-{stamp}.pdf"
    page = _open_render_tab()
    try:
        cv_markdown_to_pdf(cv_markdown, out, page=page)
    finally:
        _close_render_tab(page)
    return out


def _record_submission_and_mark_done(request_id: str, listing_id: str, draft_id: str) -> None:
    record_submission(listing_id, draft_id, channel="external_apply", notes=None)
    mark_apply_request_done(request_id, executed_draft_id=draft_id, notes=None)


def process_one(row: dict[str, Any]) -> None:
    """Dispatch a single apply_request. All errors are caught; the row is marked
    failed so the worker loop survives. Stale-claim recovery handles crashes
    that prevent us from reaching either done- or failed-mark."""
    request_id = row["id"]
    try:
        listing = _fetch_listing(row["listing_id"])
        if listing is None:
            raise RuntimeError(f"listing {row['listing_id']} not found")
        draft = _fetch_latest_draft(row["listing_id"])
        if draft is None:
            raise RuntimeError(f"no draft for listing {row['listing_id']}")

        cv_pdf_path = _render_cv_pdf(draft["adapted_cv"])

        from jobscout.apply import external_ats

        external_ats.apply(
            ats_url=_ats_url_for(listing),
            proposal=draft["body"],
            cv_pdf_path=cv_pdf_path,
            listing_title=listing.get("title") or "",
            listing_description=listing.get("description") or "",
            adapted_cv_md=draft["adapted_cv"],
        )
        _record_submission_and_mark_done(request_id, listing["id"], draft["id"])
    except Exception as e:
        log.exception("apply request %s failed", request_id)
        mark_apply_request_failed(request_id, error=str(e), notes=None)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    recovered = recover_stale_apply_claims()
    if recovered:
        log.info("recovered %d stale claim(s)", recovered)
    processed = 0
    while True:
        row = claim_one_pending_apply_request()
        if row is None:
            break
        log.info("processing apply_request %s (source=%s)", row["id"], row["source"])
        process_one(row)
        processed += 1
    log.info("worker done — processed %d request(s)", processed)
    return 0


if __name__ == "__main__":
    sys.exit(main())

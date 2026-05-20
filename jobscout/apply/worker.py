"""Apply-queue worker — picks up pending apply_requests rows and runs
the matching apply module locally on the user's Mac. Invoked every 5 min
by macOS launchd via scripts/apply-worker-local.sh.

Reads from cloud Supabase, dispatches to the existing per-source apply
modules. The user still clicks Submit on the Mac — the worker only fills.
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

from jobscout.db import (
    claim_one_pending_apply_request,
    get_latest_draft_for_listing,
    get_listing_by_id,
    mark_apply_request_done,
    mark_apply_request_failed,
    recover_stale_apply_claims,
)

log = logging.getLogger("apply-worker")


def _fetch_listing(listing_id: str) -> dict[str, Any] | None:
    return get_listing_by_id(listing_id)


def _fetch_latest_draft(listing_id: str) -> dict[str, Any] | None:
    return get_latest_draft_for_listing(listing_id)


def _render_cv_pdf(cv_markdown: str, **_kwargs: object) -> Path:
    """Render the adapted CV markdown to a PDF and return its path.

    Filename: `izabel-cvetkovic-cv-<YYYYMMDD-HHMMSS>.pdf`. Name starts with
    the candidate so the recipient instantly recognises the attachment;
    UTC timestamp suffix guarantees uniqueness across queued requests.
    """
    from datetime import UTC, datetime

    from jobscout.cv_render import cv_markdown_to_pdf

    stamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    out = Path(tempfile.gettempdir()) / f"izabel-cvetkovic-cv-{stamp}.pdf"
    cv_markdown_to_pdf(cv_markdown, out)
    return out


def process_one(row: dict[str, Any]) -> None:
    """Dispatch a single apply_request to the right per-source apply module.

    All errors are caught and marked as `failed` on the row so the loop
    survives. Stale-claim recovery handles the case where this function
    itself crashes before marking the row done/failed.
    """
    request_id = row["id"]
    try:
        listing = _fetch_listing(row["listing_id"])
        if listing is None:
            raise RuntimeError(f"listing {row['listing_id']} not found")
        draft = _fetch_latest_draft(row["listing_id"])
        if draft is None:
            raise RuntimeError(f"no draft for listing {row['listing_id']}")
        cv_pdf_path = _render_cv_pdf(
            draft["adapted_cv"], listing_id=row["listing_id"], draft_id=draft["id"]
        )

        source = row["source"]
        if source == "upwork":
            from jobscout.apply import upwork as upwork_mod

            upwork_mod.apply(
                listing["url"],
                draft["body"],
                cv_pdf_path,
                listing_title=listing.get("title") or "",
                listing_description=listing.get("description") or "",
                adapted_cv_md=draft["adapted_cv"],
            )
        elif source == "freelancermap":
            from jobscout.apply import freelancermap as fm_mod

            fm_mod.apply(listing["url"], draft["body"], cv_pdf_path)
        elif source in ("bundesagentur", "linkedin"):
            from jobscout.apply import external_ats

            ats_url = (listing.get("raw") or {}).get("externeUrl") or listing["url"]
            external_ats.apply(
                ats_url=ats_url,
                proposal=draft["body"],
                cv_pdf_path=cv_pdf_path,
                listing_title=listing.get("title") or "",
                listing_description=listing.get("description") or "",
                adapted_cv_md=draft["adapted_cv"],
            )
        else:
            raise RuntimeError(f"unknown source: {source!r}")

        mark_apply_request_done(request_id, executed_draft_id=draft["id"], notes=None)
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

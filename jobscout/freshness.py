"""Listing freshness sweep — marks dead/closed listings as EXPIRED.

The sweep is idempotent. Only listings in non-terminal states
(`NEW`, `SCORED`, `DRAFTED`, `COPIED`) are checked — `SUBMITTED`, `WON`,
`REJECTED`, `EXPIRED` are left alone.
"""

from __future__ import annotations

import argparse
import logging
import re

import httpx

from jobscout.db import list_pipeline_listings_legacy, update_listing_status
from jobscout.models import ListingStatus, Source
from jobscout.sources.base import CONTACT_UA

log = logging.getLogger("freshness")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_HTTP_TIMEOUT = 15.0

# Source-specific dead-listing markers. Regex matched against the response body.
_DEAD_MARKERS: dict[str, re.Pattern[str]] = {
    Source.LINKEDIN.value: re.compile(
        r"no longer accepting applications|job__flavor--closed|posting (?:is )?closed",
        re.I,
    ),
    Source.INDEED.value: re.compile(
        r"this job is no longer (?:available|accepting applications)|job posting expired",
        re.I,
    ),
}

# Statuses we sweep — terminal states are excluded.
_LIVE_STATUSES = (
    ListingStatus.NEW,
    ListingStatus.SCORED,
    ListingStatus.DRAFTED,
    ListingStatus.COPIED,
)


def is_listing_alive(url: str, source: str) -> bool | None:
    """Return True (alive), False (dead), or None (couldn't determine).
    Network errors and unsupported sources return None — the caller leaves
    the status untouched rather than guessing wrong."""
    marker = _DEAD_MARKERS.get(source)
    if marker is None:
        return None
    try:
        with httpx.Client(headers={"User-Agent": CONTACT_UA}, timeout=_HTTP_TIMEOUT, follow_redirects=True) as c:
            r = c.get(url)
    except (httpx.HTTPError, OSError):
        return None
    if r.status_code == 404:
        return False
    if r.status_code != 200:
        return None
    return not bool(marker.search(r.text))


def sweep() -> tuple[int, int, int]:
    """Walk every live listing, mark dead ones EXPIRED.
    Returns (checked, expired, errors_or_skipped). `update_listing_status`
    only writes the fields passed in, so score/rationale survive."""
    rows = list_pipeline_listings_legacy(statuses=list(_LIVE_STATUSES))
    checked = 0
    expired = 0
    skipped = 0
    for row in rows:
        url = row.get("url")
        source = row.get("source")
        listing_id = row.get("id")
        if not url or not source or not listing_id:
            skipped += 1
            continue
        alive = is_listing_alive(url, source)
        checked += 1
        if alive is False:
            update_listing_status(str(listing_id), ListingStatus.EXPIRED)
            expired += 1
            log.info("expired: %s | %s", source, url)
        elif alive is None:
            skipped += 1
    return checked, expired, skipped


def main() -> None:
    ap = argparse.ArgumentParser(description="Freshness sweep — mark dead listings as EXPIRED")
    ap.add_argument("--dry-run", action="store_true", help="Print what would change without writing")
    args = ap.parse_args()
    if args.dry_run:
        rows = list_pipeline_listings_legacy(statuses=list(_LIVE_STATUSES))
        dead = [r for r in rows if is_listing_alive(r["url"], r["source"]) is False]
        log.info("[dry-run] would expire %d / %d", len(dead), len(rows))
        for r in dead:
            log.info("[dry-run] %s | %s", r["source"], r["url"])
        return
    checked, expired, skipped = sweep()
    log.info("checked=%d expired=%d skipped/inconclusive=%d", checked, expired, skipped)


if __name__ == "__main__":
    main()

"""Listing freshness sweep — marks dead/closed listings as EXPIRED.

The sweep is idempotent. Only listings in non-terminal states
(`NEW`, `SCORED`, `DRAFTED`, `COPIED`) are checked — `SUBMITTED`, `WON`,
`REJECTED`, `EXPIRED` are left alone.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from jobscout.db import list_pipeline_listings_legacy, list_source_runs, update_listing_status
from jobscout.models import ListingStatus, Source
from jobscout.sources.base import CONTACT_UA

log = logging.getLogger("freshness")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_HTTP_TIMEOUT = 15.0

# "Dropped out of the scrape" expiry. Page-refetch detection is unreliable
# (Indeed 403-blocks httpx, closed LinkedIn jobs hide the closure text), so the
# reliable signal is that the source kept scraping successfully but stopped
# returning the listing. `discovered_at` is rewritten on every scrape (see
# db.upsert_listing), so it doubles as "last seen in a scrape".
_STALE_MISSES = int(os.environ.get("FRESHNESS_STALE_MISSES", "2"))
_STALE_MIN_AGE_DAYS = int(os.environ.get("FRESHNESS_STALE_MIN_AGE_DAYS", "7"))

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


def _select_stale(
    listings: list[dict[str, Any]],
    successful_run_times: dict[str, list[datetime]],
    *,
    misses: int,
    min_age_days: int,
    now: datetime,
) -> list[str]:
    """IDs of listings the source dropped from its scrape. A listing qualifies
    when its source scraped SUCCESSFULLY at least `misses` times after the
    listing was last seen (`discovered_at`) yet never re-returned it — and it's
    older than `min_age_days`. The successful-run gate means a failed or empty
    scrape never expires anything; the age floor keeps anything recent safe."""
    stale: list[str] = []
    for row in listings:
        seen_raw, lid = row.get("discovered_at"), row.get("id")
        if not seen_raw or not lid:
            continue
        seen = datetime.fromisoformat(seen_raw)
        if (now - seen).days < min_age_days:
            continue
        misses_since = sum(1 for t in successful_run_times.get(row.get("source", ""), []) if t > seen)
        if misses_since >= misses:
            stale.append(str(lid))
    return stale


def _successful_run_times() -> dict[str, list[datetime]]:
    """Per-source finish times of runs that actually returned listings."""
    out: dict[str, list[datetime]] = {}
    for r in list_source_runs(limit=200):
        if r.get("error") is None and (r.get("listings_found") or 0) > 0 and r.get("finished_at"):
            out.setdefault(r["source"], []).append(datetime.fromisoformat(r["finished_at"]))
    return out


def expire_stale(*, dry_run: bool = False) -> list[str]:
    """Expire listings that dropped out of the scrape (see _select_stale)."""
    listings = list_pipeline_listings_legacy(statuses=list(_LIVE_STATUSES))
    stale = _select_stale(
        listings,
        _successful_run_times(),
        misses=_STALE_MISSES,
        min_age_days=_STALE_MIN_AGE_DAYS,
        now=datetime.now(UTC),
    )
    if not dry_run:
        for lid in stale:
            update_listing_status(lid, ListingStatus.EXPIRED)
    log.info("%sstale-expire: %d / %d pipeline listings", "[dry-run] " if dry_run else "", len(stale), len(listings))
    return stale


def main() -> None:
    ap = argparse.ArgumentParser(description="Freshness sweep — mark dead / dropped listings as EXPIRED")
    ap.add_argument("--dry-run", action="store_true", help="Print what would change without writing")
    args = ap.parse_args()
    if args.dry_run:
        rows = list_pipeline_listings_legacy(statuses=list(_LIVE_STATUSES))
        dead = [r for r in rows if is_listing_alive(r["url"], r["source"]) is False]
        log.info("[dry-run] marker-dead would expire %d / %d", len(dead), len(rows))
        expire_stale(dry_run=True)
        return
    checked, expired, skipped = sweep()
    log.info("checked=%d expired=%d skipped/inconclusive=%d", checked, expired, skipped)
    dropped = expire_stale()
    log.info("stale-dropped expired=%d", len(dropped))


if __name__ == "__main__":
    main()

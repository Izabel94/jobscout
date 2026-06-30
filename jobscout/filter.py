"""Filter stage: applies all 4 hard filters to status='new' listings."""

import logging

from jobscout.config_loader import load_spam_rules
from jobscout.db import list_pipeline_listings_legacy, update_listing_status
from jobscout.filters import (
    duplicate_ids,
    has_hard_drop_pattern,
    pass_embedding,
    pass_skill_match,
    pass_structural,
    pass_title_denylist,
    spam_score,
)
from jobscout.models import Listing, ListingStatus

log = logging.getLogger("filter")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_ACTIVE_STATUSES = [ListingStatus.NEW, ListingStatus.SCORED, ListingStatus.DRAFTED]


def _prepass_reject_dupes() -> None:
    """Reject cross-run duplicates across all active listings — not just new
    ones — so rows already in the UI get cleaned too. Agencies are judged by the
    LLM scorer (red flag 'agency'), not here. Runs before the per-listing hard
    filters."""
    active = [Listing.model_validate(r) for r in list_pipeline_listings_legacy(_ACTIVE_STATUSES, limit=10_000)]
    dupes = set(duplicate_ids(active))
    for listing_id in dupes:
        update_listing_status(listing_id, ListingStatus.REJECTED)
    log.info("prepass: rejected %d duplicate listing(s)", len(dupes))


def main() -> None:
    _prepass_reject_dupes()
    rows = list_pipeline_listings_legacy([ListingStatus.NEW], limit=10_000)
    log.info("filtering %d new listings", len(rows))
    threshold = load_spam_rules()["spam_score_drop_threshold"]
    for row in rows:
        listing = Listing.model_validate(row)
        listing_id = str(row["id"])
        if not pass_structural(listing):
            update_listing_status(listing_id, ListingStatus.REJECTED)
            continue
        if has_hard_drop_pattern(listing):
            update_listing_status(listing_id, ListingStatus.REJECTED, spam_score=99)
            continue
        score = spam_score(listing)
        if score >= threshold:
            update_listing_status(listing_id, ListingStatus.REJECTED, spam_score=score)
            continue
        if not pass_skill_match(listing):
            update_listing_status(listing_id, ListingStatus.REJECTED)
            continue
        if not pass_title_denylist(listing):
            update_listing_status(listing_id, ListingStatus.REJECTED)
            continue
        if not pass_embedding(listing):
            update_listing_status(listing_id, ListingStatus.REJECTED)
            continue
        update_listing_status(listing_id, ListingStatus.NEW, spam_score=score)


if __name__ == "__main__":
    main()

"""Per-source apply automation.

Each module under `jobscout.apply.*` exports an `apply(listing, proposal)`
function that opens the listing in a Playwright window with a persistent
profile (so login cookies survive), fills the per-site application form,
and PAUSES at the final Submit button so the user reviews and clicks.

Helpers here (daily-cap accounting) are source-agnostic.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast

from jobscout.db import _client


def submissions_today(source: str) -> int:
    """Return the number of submissions for `source` made in the last 24h.

    Used to enforce per-source daily caps so the apply automation doesn't
    look like mass scraping.
    """
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    res = (
        _client()
        .table("submissions")
        .select("id, submitted_at, listings!inner(source)")
        .gte("submitted_at", cutoff)
        .execute()
    )
    rows = cast(list[dict[str, Any]], res.data or [])
    return sum(1 for r in rows if (r.get("listings") or {}).get("source") == source)

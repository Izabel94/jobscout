"""Single-listing renderer (cards + helpers).

Helpers are pure functions, unit-tested. The render functions land in Task 5
and are Streamlit-dependent (tested via Playwright MCP smoke)."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

from jobscout.models import ApplyMethod, Arrangement, JobType


def score_pill_class(score: int | None) -> str:
    if score is None or score < 60:
        return "jobscout-score jobscout-score-low"
    if score < 80:
        return "jobscout-score jobscout-score-mid"
    return "jobscout-score jobscout-score-high"


def favicon_url(listing_url: str, company_url_direct: str | None) -> str:
    """Prefer company_url_direct's host over the job-board host. Drop the
    leftmost subdomain label (www., jobs., boards., ...) when the host has
    3+ parts so the favicon resolves to the registered domain."""
    candidate = company_url_direct or listing_url
    try:
        host = urlparse(candidate).hostname or ""
    except Exception:
        host = ""
    parts = host.split(".")
    if len(parts) >= 3:
        host = ".".join(parts[1:])
    if not host:
        host = "example.com"
    return f"https://www.google.com/s2/favicons?domain={host}&sz=32"


def short_relative_time(when: datetime | None) -> str:
    if when is None:
        return ""
    now = datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta = now - when
    seconds = int(delta.total_seconds())
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def arrangement_badge_class(arr: Arrangement | None) -> str:
    suffix = {
        Arrangement.REMOTE: "remote",
        Arrangement.HYBRID: "hybrid",
        Arrangement.ONSITE: "onsite",
        Arrangement.UNKNOWN: "unknown-arr",
    }.get(arr, "unknown-arr")
    return f"jobscout-badge jobscout-badge-{suffix}"


def job_type_badge_class(jt: JobType | None) -> str:
    if jt in (JobType.FULLTIME, JobType.PERMANENT):
        return f"jobscout-badge jobscout-badge-{jt.value}"
    return "jobscout-badge jobscout-badge-dropped"


def apply_method_badge_class(am: ApplyMethod | None) -> str:
    if am == ApplyMethod.EXTERNAL_APPLY:
        return "jobscout-badge jobscout-badge-external"
    return "jobscout-badge jobscout-badge-easy"


# render() and other Streamlit-dependent functions land in Task 5.

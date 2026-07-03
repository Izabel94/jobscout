"""Unit tests for the 'dropped out of the scrape' staleness selector."""

from datetime import UTC, datetime, timedelta

from jobscout.freshness import _select_stale

_NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)


def _iso(days_ago: float) -> str:
    return (_NOW - timedelta(days=days_ago)).isoformat()


def _runs(source: str, *days_ago: float) -> dict[str, list[datetime]]:
    return {source: [_NOW - timedelta(days=d) for d in days_ago]}


def test_expires_when_enough_successful_runs_missed_it():
    listings = [{"id": "a", "source": "linkedin", "discovered_at": _iso(20)}]
    # two successful scrapes since it was last seen, neither re-found it
    stale = _select_stale(listings, _runs("linkedin", 1, 3), misses=2, min_age_days=7, now=_NOW)
    assert stale == ["a"]


def test_kept_when_recently_seen():
    listings = [{"id": "a", "source": "linkedin", "discovered_at": _iso(1)}]
    stale = _select_stale(listings, _runs("linkedin", 0.5), misses=2, min_age_days=7, now=_NOW)
    assert stale == []  # younger than min_age floor


def test_min_age_floor_protects_recent_even_with_many_misses():
    listings = [{"id": "a", "source": "linkedin", "discovered_at": _iso(3)}]
    # 5 successful runs missed it, but it's only 3 days old -> floor keeps it
    stale = _select_stale(listings, _runs("linkedin", 0, 1, 2, 2.5, 2.9), misses=2, min_age_days=7, now=_NOW)
    assert stale == []


def test_failed_or_empty_scrapes_do_not_count():
    # An old listing, but its source has had NO successful runs since (only
    # failed/empty ones, which the caller filters out) -> must not expire.
    listings = [{"id": "a", "source": "indeed", "discovered_at": _iso(30)}]
    stale = _select_stale(listings, {"indeed": []}, misses=2, min_age_days=7, now=_NOW)
    assert stale == []


def test_needs_at_least_n_misses():
    listings = [{"id": "a", "source": "linkedin", "discovered_at": _iso(20)}]
    # only ONE successful run since last seen; N=2 required
    stale = _select_stale(listings, _runs("linkedin", 1), misses=2, min_age_days=7, now=_NOW)
    assert stale == []


def test_only_runs_after_last_seen_count():
    listings = [{"id": "a", "source": "linkedin", "discovered_at": _iso(20)}]
    # both successful runs happened BEFORE it was last seen (25, 30 days ago)
    stale = _select_stale(listings, _runs("linkedin", 25, 30), misses=2, min_age_days=7, now=_NOW)
    assert stale == []

from __future__ import annotations

from urllib.parse import urlparse

from jobscout.ui.card import (
    favicon_url,
    score_pill_class,
    short_relative_time,
    arrangement_badge_class,
    job_type_badge_class,
    apply_method_badge_class,
)
from jobscout.models import Arrangement, ApplyMethod, JobType


def test_score_pill_class_thresholds():
    assert score_pill_class(95) == "jobscout-score jobscout-score-high"
    assert score_pill_class(80) == "jobscout-score jobscout-score-high"
    assert score_pill_class(79) == "jobscout-score jobscout-score-mid"
    assert score_pill_class(60) == "jobscout-score jobscout-score-mid"
    assert score_pill_class(59) == "jobscout-score jobscout-score-low"
    assert score_pill_class(0) == "jobscout-score jobscout-score-low"
    assert score_pill_class(None) == "jobscout-score jobscout-score-low"


def test_favicon_url_from_listing_url():
    url = favicon_url("https://www.linkedin.com/jobs/view/123", company_url_direct=None)
    assert url == "https://www.google.com/s2/favicons?domain=linkedin.com&sz=32"


def test_favicon_url_prefers_company_url_direct():
    # When company_url_direct is set, use its host (stripping www./jobs. prefixes)
    url = favicon_url(
        "https://www.linkedin.com/jobs/view/123",
        company_url_direct="https://boards.greenhouse.io/otto/jobs/4567",
    )
    # We don't try to recover otto.de from the greenhouse URL — that would be
    # heuristic. We use the ATS host (greenhouse.io) which is at least more
    # useful than 'linkedin.com'.
    assert url == "https://www.google.com/s2/favicons?domain=greenhouse.io&sz=32"


def test_favicon_url_strips_www_prefix():
    url = favicon_url("https://www.otto.de/karriere/123", company_url_direct=None)
    assert url == "https://www.google.com/s2/favicons?domain=otto.de&sz=32"


def test_short_relative_time():
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    assert short_relative_time(now - timedelta(minutes=5)) == "5m ago"
    assert short_relative_time(now - timedelta(hours=2)) == "2h ago"
    assert short_relative_time(now - timedelta(days=3)) == "3d ago"
    assert short_relative_time(now - timedelta(days=10)) == "10d ago"
    assert short_relative_time(None) == ""


def test_arrangement_badge_class():
    assert arrangement_badge_class(Arrangement.REMOTE) == "jobscout-badge jobscout-badge-remote"
    assert arrangement_badge_class(Arrangement.HYBRID) == "jobscout-badge jobscout-badge-hybrid"
    assert arrangement_badge_class(Arrangement.ONSITE) == "jobscout-badge jobscout-badge-onsite"
    assert arrangement_badge_class(Arrangement.UNKNOWN) == "jobscout-badge jobscout-badge-unknown-arr"


def test_job_type_badge_class():
    assert job_type_badge_class(JobType.FULLTIME) == "jobscout-badge jobscout-badge-fulltime"
    assert job_type_badge_class(JobType.PERMANENT) == "jobscout-badge jobscout-badge-permanent"
    # Anything non-fulltime/permanent is "dropped" styled (shouldn't appear in pipeline anyway,
    # but defensive)
    assert job_type_badge_class(JobType.CONTRACT) == "jobscout-badge jobscout-badge-dropped"


def test_apply_method_badge_class():
    assert apply_method_badge_class(ApplyMethod.EXTERNAL_APPLY) == "jobscout-badge jobscout-badge-external"
    assert apply_method_badge_class(ApplyMethod.EASY_APPLY) == "jobscout-badge jobscout-badge-easy"

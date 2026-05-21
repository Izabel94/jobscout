"""Inverted filter rules for jobscout:
- DROP if job_type_classified ∈ {CONTRACT, PARTTIME, INTERN}
- DROP if arrangement == ONSITE and arrangement_evidence is high-confidence
- KEEP otherwise (including UNKNOWN arrangement, UNKNOWN job_type)
- DON'T filter on rate (full-time DE listings often omit salary)
"""

from __future__ import annotations

from jobscout.filters import pass_structural
from jobscout.models import (
    ApplyMethod,
    Arrangement,
    JobType,
    Listing,
    Source,
)


def _listing(**overrides) -> Listing:
    base = dict(
        source=Source.LINKEDIN,
        source_id="x",
        url="https://linkedin.com/jobs/view/1",
        title="ML Engineer",
        description="some description",
        location="Hamburg",
        raw={},
        arrangement=Arrangement.REMOTE,
        job_type_classified=JobType.FULLTIME,
        apply_method=ApplyMethod.EASY_APPLY,
    )
    base.update(overrides)
    return Listing(**base)


def test_drop_contract():
    assert pass_structural(_listing(job_type_classified=JobType.CONTRACT)) is False


def test_drop_parttime():
    assert pass_structural(_listing(job_type_classified=JobType.PARTTIME)) is False


def test_drop_intern():
    assert pass_structural(_listing(job_type_classified=JobType.INTERN)) is False


def test_keep_fulltime():
    assert pass_structural(_listing(job_type_classified=JobType.FULLTIME)) is True


def test_keep_permanent():
    assert pass_structural(_listing(job_type_classified=JobType.PERMANENT)) is True


def test_keep_unknown_job_type():
    assert pass_structural(_listing(job_type_classified=JobType.UNKNOWN)) is True


def test_drop_high_confidence_onsite():
    assert pass_structural(
        _listing(arrangement=Arrangement.ONSITE, arrangement_evidence="5 days/week in office")
    ) is False


def test_drop_high_confidence_onsite_german():
    assert pass_structural(
        _listing(arrangement=Arrangement.ONSITE, arrangement_evidence="vollständig vor ort")
    ) is False


def test_keep_low_confidence_onsite():
    # arrangement=ONSITE but no high-confidence evidence — pass through (let LLM decide)
    assert pass_structural(
        _listing(arrangement=Arrangement.ONSITE, arrangement_evidence="büro")
    ) is True


def test_keep_hybrid():
    assert pass_structural(_listing(arrangement=Arrangement.HYBRID, arrangement_evidence="hybrid")) is True


def test_keep_unknown_arrangement():
    assert pass_structural(_listing(arrangement=Arrangement.UNKNOWN, arrangement_evidence="")) is True


def test_keep_listing_with_no_rate():
    assert pass_structural(_listing(rate_min=None, rate_max=None)) is True

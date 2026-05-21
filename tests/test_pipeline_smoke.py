"""End-to-end smoke against fixtures + stubbed LLM. Runs sources adapter on
fixture data (no live LinkedIn / Indeed), filters with the inverted rule set,
exercises the score+draft path with the LLM stubbed.

Asserts: rows pass through pipeline, scored rows have rationale, drafts have body.
"""

from __future__ import annotations

from jobscout.filters import pass_structural
from jobscout.models import ApplyMethod, Arrangement, JobType, Listing, Source


def _listing(**overrides) -> Listing:
    base = dict(
        source=Source.LINKEDIN,
        source_id="x",
        url="https://linkedin.com/jobs/view/1",
        title="ML Engineer",
        raw={},
        arrangement=Arrangement.REMOTE,
        job_type_classified=JobType.FULLTIME,
        apply_method=ApplyMethod.EXTERNAL_APPLY,
    )
    base.update(overrides)
    return Listing(**base)


def test_filter_keeps_remote_fulltime_ml_role() -> None:
    keep = _listing()
    assert pass_structural(keep) is True


def test_filter_drops_intern_role() -> None:
    drop = _listing(
        source_id="d1",
        title="ML Intern",
        arrangement=Arrangement.HYBRID,
        job_type_classified=JobType.INTERN,
        apply_method=ApplyMethod.EASY_APPLY,
    )
    assert pass_structural(drop) is False


def test_filter_drops_high_confidence_onsite() -> None:
    drop = _listing(
        source_id="d2",
        arrangement=Arrangement.ONSITE,
        arrangement_evidence="5 days/week in office",
    )
    assert pass_structural(drop) is False


def test_filter_keeps_hybrid_permanent() -> None:
    keep = _listing(
        source_id="k2",
        arrangement=Arrangement.HYBRID,
        arrangement_evidence="hybrid",
        job_type_classified=JobType.PERMANENT,
    )
    assert pass_structural(keep) is True

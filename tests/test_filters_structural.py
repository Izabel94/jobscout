from decimal import Decimal
from typing import Any

from jobscout.filters import pass_structural
from jobscout.models import Listing, RateUnit, Source


def _l(**kw: Any) -> Listing:
    base: dict[str, Any] = dict(
        source=Source.UPWORK,
        source_id="x",
        url="https://x",
        title="LangChain RAG engineer",
        description="Build a RAG system with LangChain and Anthropic Claude over a Postgres pgvector store. " * 5,
        remote=True,
        rate_max=Decimal(90),
        rate_unit=RateUnit.HOUR,
        currency="EUR",
        hours_per_week=None,
        language="en",
        raw={},
    )
    base.update(kw)
    return Listing(**base)


def test_keeps_clean() -> None:
    assert pass_structural(_l()) is True


def test_drops_not_remote() -> None:
    assert pass_structural(_l(remote=False)) is False


def test_drops_rate_below_floor() -> None:
    assert pass_structural(_l(rate_max=Decimal(40))) is False


def test_drops_hours_above_10() -> None:
    assert pass_structural(_l(hours_per_week=Decimal(20))) is False


def test_keeps_null_hours() -> None:
    assert pass_structural(_l(hours_per_week=None)) is True


def test_drops_fulltime() -> None:
    assert pass_structural(_l(description="full-time only, 40h/week")) is False


def test_drops_40_hours_per_week_with_spaces() -> None:
    """LinkedIn often writes '40 Hours / Week' with spacing the old regex missed."""
    assert pass_structural(_l(description="* 40 Hours / Week\nWork closely with…")) is False


def test_drops_30_hours_per_week() -> None:
    """Any explicit workload above max_hours_per_week (10) drops, not just 40."""
    assert pass_structural(_l(description="Looking for ~30 hours per week commitment.")) is False


def test_drops_german_stunden() -> None:
    assert pass_structural(_l(description="35 Std pro Woche, remote möglich.")) is False


def test_keeps_low_hours_per_week() -> None:
    """5-10 hours/week is exactly what we want — must NOT trigger the drop."""
    assert pass_structural(_l(description="Approx 8 hours per week, async.")) is True


def test_keeps_flexible_range_with_low_end_in_window() -> None:
    """'10-40 hours/week' is fine — candidate can stay at the low end."""
    assert pass_structural(_l(description="Commitment: 10-40 hours/week, remote.")) is True


def test_drops_range_with_low_end_above_window() -> None:
    """'20-40 hours/week' minimum 20h still exceeds the 10h cap."""
    assert pass_structural(_l(description="Commitment: 20-40 hours/week.")) is False


def test_keeps_unrelated_hours_mention() -> None:
    """'Respond within 24 hours' is an SLA, not a workload — must NOT drop."""
    desc = "Please respond within 24 hours. " + "x " * 100
    assert pass_structural(_l(description=desc)) is True


def test_keeps_when_minimum_commitment_is_in_window() -> None:
    """Listings that name both a minimum and a maximum keep on minimum."""
    desc = "Minimum 10 hrs/week, up to 40 hrs/week, flexible scheduling."
    assert pass_structural(_l(description=desc)) is True


def test_drops_other_language() -> None:
    assert pass_structural(_l(language="fr")) is False


def test_drops_linkedin_fulltime_via_job_type() -> None:
    """LinkedIn rows often imply full-time without the literal phrase appearing
    in the description. Drop based on JobSpy's normalized `job_type`."""
    assert pass_structural(_l(source=Source.LINKEDIN, raw={"job_type": "fulltime"})) is False


def test_keeps_linkedin_contract_job_type() -> None:
    assert pass_structural(_l(source=Source.LINKEDIN, raw={"job_type": "contract"})) is True


def test_keeps_when_job_type_missing() -> None:
    """Sources without JobSpy-style job_type metadata aren't affected."""
    assert pass_structural(_l(source=Source.BUNDESAGENTUR, raw={"refnr": "12345"})) is True


def test_drops_freelancermap_100pct_auslastung() -> None:
    """`100% Auslastung` in the FM sidebar implies a 40h/week commitment."""
    desc = "100% Auslastung | 100% Remote | Freiberuflich\n\nBuild a RAG system with LangChain."
    assert pass_structural(_l(source=Source.FREELANCERMAP, description=desc, language="de")) is False


def test_drops_freelancermap_80pct_auslastung() -> None:
    """80% Auslastung = 32h/week — still over the 10h cap, must drop."""
    desc = "80% Auslastung | Remote\n\nBuild a RAG system."
    assert pass_structural(_l(source=Source.FREELANCERMAP, description=desc, language="de")) is False


def test_keeps_freelancermap_20pct_auslastung() -> None:
    """20% Auslastung = 8h/week — fits under the 10h cap."""
    desc = "20% Auslastung | 100% Remote\n\nBuild a RAG system with LangChain."
    assert pass_structural(_l(source=Source.FREELANCERMAP, description=desc, language="de")) is True


def test_drops_auslastung_reverse_order() -> None:
    """Inline body text uses `Auslastung 80-100 %` (German en-dash) order."""
    desc = "Auslastung 80–90 %\n\nLangChain RAG."  # noqa: RUF001
    assert pass_structural(_l(source=Source.FREELANCERMAP, description=desc, language="de")) is False


def test_drops_festanstellung() -> None:
    """`Festanstellung` (permanent employment) is full-time-by-definition."""
    desc = "Type: Festanstellung\n\nLangChain engineer needed."
    assert pass_structural(_l(source=Source.FREELANCERMAP, description=desc, language="de")) is False

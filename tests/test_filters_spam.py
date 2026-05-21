from decimal import Decimal
from typing import Any

from jobscout.filters import has_hard_drop_pattern, spam_score
from jobscout.models import Listing, RateUnit, Source


def _l(**kw: Any) -> Listing:
    base: dict[str, Any] = dict(
        source=Source.LINKEDIN,
        source_id="x",
        url="https://x",
        title="LangChain engineer",
        description=(
            "Build a production RAG pipeline with LangGraph and Postgres pgvector. "
            "Stack: Python, LangChain, Neo4j. Contact: Jane Doe — https://linkedin.com/in/janedoe."
        ),
        raw={},
    )
    base.update(kw)
    return Listing(**base)


def test_clean_listing_low_score() -> None:
    assert spam_score(_l()) <= 0


def test_upfront_fee_hard_drop() -> None:
    assert has_hard_drop_pattern(_l(description="Pay a $50 registration fee to start.")) is True


def test_unpaid_trial_hard_drop() -> None:
    assert has_hard_drop_pattern(_l(description="Test task before payment, then we discuss salary.")) is True


def test_mlm_keyword_hard_drop() -> None:
    assert has_hard_drop_pattern(_l(description="Strukturvertrieb, nebenberuflich Vermögensaufbau.")) is True


def test_dvag_company_hard_drop() -> None:
    assert has_hard_drop_pattern(_l(description="DVAG Finanzberater gesucht.")) is True


def test_takehome_task_hard_drop() -> None:
    assert (
        has_hard_drop_pattern(_l(description="Please complete this 4-hour take-home task and submit a Loom intro."))
        is True
    )


def test_video_intro_hard_drop() -> None:
    assert has_hard_drop_pattern(_l(description="Record a short intro video explaining your approach.")) is True


def test_coding_challenge_hard_drop() -> None:
    assert has_hard_drop_pattern(_l(description="Coding challenge required to apply.")) is True


def test_rag_low_budget_b1() -> None:
    listing = _l(
        description="Build a full RAG system end-to-end. Budget: $500 fixed.",
        rate_max=Decimal(500),
        rate_unit=RateUnit.FIXED,
        currency="USD",
    )
    assert spam_score(listing) >= 3


def test_short_no_concrete_a2() -> None:
    assert spam_score(_l(title="AI Expert Needed Urgent", description="Need AI expert ASAP DM me")) >= 2


def test_autotranslation_f2() -> None:
    assert (
        spam_score(
            _l(
                description=(
                    "Greetings of the day. Kindly do the needful and revert. "
                    "We have informations about the project. Since 5 years we run AI projects."
                )
            )
        )
        >= 2
    )

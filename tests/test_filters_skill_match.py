from typing import Any

import pytest

from jobscout.filters import pass_skill_match, pass_title_denylist
from jobscout.models import Listing, Source


@pytest.fixture(autouse=True)
def _profile(monkeypatch):
    monkeypatch.setattr(
        "jobscout.filters.load_profile",
        lambda: {
            "required_skill_keywords": ["LangChain", "LangGraph", "RAG", "Neo4j", "Python"],
            "title_denylist": ["WordPress"],
        },
    )


def _l(**kw: Any) -> Listing:
    base: dict[str, Any] = dict(
        source=Source.LINKEDIN,
        source_id="x",
        url="https://x",
        title="t",
        description="",
        raw={},
    )
    base.update(kw)
    return Listing(**base)


def test_skill_match_langchain() -> None:
    assert pass_skill_match(_l(description="LangChain RAG engineer needed")) is True


def test_skill_match_neo4j() -> None:
    assert pass_skill_match(_l(description="Build knowledge graph in Neo4j")) is True


def test_skill_no_match() -> None:
    assert pass_skill_match(_l(description="WordPress developer needed")) is False


def test_title_deny_wordpress() -> None:
    assert pass_title_denylist(_l(title="WordPress AI plugin developer")) is False


def test_title_deny_clean() -> None:
    assert pass_title_denylist(_l(title="LangChain AI engineer")) is True


# --- token-based matching: role-phrase keywords must match on their meaningful
# tokens, not verbatim, so varied on-target titles still pass. ---

_MARKETING_KEYWORDS = [
    "Online Marketing Manager",
    "Paid Media Manager",
    "Digital Marketing Manager",
    "Programmatic Manager",
    "Performance Marketing Manager",
]


def _marketing_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        "jobscout.filters.load_profile",
        lambda: {"required_skill_keywords": _MARKETING_KEYWORDS, "title_denylist": []},
    )


def test_skill_match_varied_title_without_verbatim_phrase(monkeypatch) -> None:
    _marketing_profile(monkeypatch)
    assert pass_skill_match(_l(title="Growth Marketing Manager (all genders)")) is True


def test_skill_match_paid_social_via_token(monkeypatch) -> None:
    _marketing_profile(monkeypatch)
    assert pass_skill_match(_l(title="Senior Paid Social Manager")) is True


def test_skill_match_rejects_offtopic_role(monkeypatch) -> None:
    _marketing_profile(monkeypatch)
    assert pass_skill_match(_l(title="SAP FI/CO Consultant", description="ERP rollout")) is False


def test_skill_match_ignores_generic_role_words(monkeypatch) -> None:
    _marketing_profile(monkeypatch)
    # "Manager" alone (a generic word stripped from the keywords) must not match.
    assert pass_skill_match(_l(title="Account Manager", description="sales quota")) is False

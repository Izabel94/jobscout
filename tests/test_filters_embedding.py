import pytest

from jobscout.filters import pass_embedding
from jobscout.models import Listing, Source


@pytest.fixture(autouse=True)
def _profile(monkeypatch):
    monkeypatch.setattr(
        "jobscout.embeddings.load_profile",
        lambda: {
            "anchor_summaries": [
                {
                    "title": "LangGraph + Neo4j knowledge graph",
                    "summary": "Built a production LangGraph agent over a Neo4j knowledge graph with Anthropic Claude planner and pgvector retrieval.",
                },
            ],
            "required_skill_keywords": ["LangChain", "LangGraph", "RAG", "Neo4j", "pgvector"],
        },
    )
    from jobscout import embeddings

    embeddings._profile_embedding.cache_clear()
    embeddings._target_role_embeddings.cache_clear()


def _l(t: str, d: str) -> Listing:
    return Listing(source=Source.LINKEDIN, source_id="x", url="https://x", title=t, description=d, raw={})


def test_relevant_passes() -> None:
    listing = _l(
        "LangGraph RAG engineer",
        "Build a production LangGraph agent that queries Neo4j and pgvector. Anthropic Claude as the planner.",
    )
    assert pass_embedding(listing) is True


def test_irrelevant_drops() -> None:
    listing = _l(
        "Roof contractor needed",
        "Looking for a roof contractor in Texas. Must have insurance.",
    )
    assert pass_embedding(listing) is False


def test_career_change_listing_passes_on_target_role(monkeypatch) -> None:
    monkeypatch.setattr(
        "jobscout.embeddings.load_profile",
        lambda: {
            "anchor_summaries": [
                {
                    "title": "Programmatic media consultant",
                    "summary": "Planned and bought programmatic display and video inventory via DSPs (DV360, "
                    "The Trade Desk), optimised CPM, viewability and brand-safety for agency clients.",
                },
                {
                    "title": "Performance marketing lead",
                    "summary": "Ran Google Ads and Meta campaigns, ROAS reporting, attribution modelling and "
                    "media budget pacing.",
                },
            ],
            "required_skill_keywords": ["Key Account Manager", "Solutions Consultant"],
        },
    )
    from jobscout import embeddings

    embeddings._profile_embedding.cache_clear()
    embeddings._target_role_embeddings.cache_clear()
    listing = _l(
        "Key Account Manager (m/w/d)",
        "Betreuung unserer Schlüsselkunden im Lebensmitteleinzelhandel, Jahresgespräche, Konditionen, Umsatzplanung.",
    )
    assert pass_embedding(listing) is True

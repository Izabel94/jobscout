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

from jobscout.filters import pass_embedding
from jobscout.models import Listing, Source


def _l(t: str, d: str) -> Listing:
    return Listing(source=Source.UPWORK, source_id="x", url="https://x", title=t, description=d, raw={})


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

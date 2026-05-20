from typing import Any

from jobscout.filters import pass_skill_match, pass_title_denylist
from jobscout.models import Listing, Source


def _l(**kw: Any) -> Listing:
    base: dict[str, Any] = dict(
        source=Source.UPWORK,
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

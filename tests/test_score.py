"""Smoke tests for score.py — verify rendering and main loop wiring without hitting an LLM."""

from decimal import Decimal
from unittest.mock import patch

from jobscout.models import Listing, ListingStatus, RateUnit, Source
from jobscout.score import _PROMPT, _render, main


def test_render_substitutes_all_placeholders() -> None:
    listing = Listing(
        source=Source.UPWORK,
        source_id="x",
        url="https://x",
        title="LangChain engineer",
        description="Build a RAG",
        rate_min=Decimal(60),
        rate_max=Decimal(90),
        rate_unit=RateUnit.HOUR,
        currency="USD",
        hours_per_week=Decimal(10),
        language="en",
        raw={},
    )
    rendered = _render(_PROMPT, listing)
    assert "{{" not in rendered, "all placeholders should be replaced"
    assert "LangChain engineer" in rendered
    assert "60" in rendered and "90" in rendered
    assert "USD" in rendered
    assert "hour" in rendered  # rate_unit value


def test_render_handles_none_fields() -> None:
    listing = Listing(
        source=Source.UPWORK,
        source_id="x",
        url="https://x",
        title="t",
        description=None,
        raw={},
    )
    rendered = _render(_PROMPT, listing)
    assert "{{" not in rendered


@patch("jobscout.score.call_json")
@patch("jobscout.score.list_unscored_new_listings")
@patch("jobscout.score.update_listing_status")
def test_main_scores_and_updates(mock_update, mock_list, mock_call) -> None:  # type: ignore[no-untyped-def]
    mock_list.return_value = [
        {
            "id": "u1",
            "source": "upwork",
            "source_id": "abc",
            "url": "https://x",
            "title": "LangChain engineer",
            "description": "Build a RAG",
            "raw": {},
        },
    ]
    mock_call.return_value = {"score": 82, "rationale": "good fit", "red_flags": []}
    main()
    mock_call.assert_called_once()
    mock_update.assert_called_once_with("u1", ListingStatus.SCORED, score=82, score_rationale="good fit")

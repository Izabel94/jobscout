"""Smoke tests for draft.py — verify wiring without hitting an LLM."""

from unittest.mock import patch

import pytest

from jobscout.draft import (
    _build_proposal_prompt,
    _extract_contact_name,
    _PROMPT_CV,
    _verify_cv_facts,
    draft_one,
)
from jobscout.models import Draft, Listing, ListingStatus, Source

_CV_BASE_EN = (
    "# Test Candidate\n\n"
    "test@example.com · <https://linkedin.example/x>\n\n"
    "**Senior Performance Marketing Manager**\n\n"
    "## Experience\n\n"
    "### Acme Corp | Berlin\n\n"
    "**Senior Manager** | *2019 – 2021*\n\n"
    "Built things.\n"
)
_CV_BASE_DE = (
    "# Test Candidate\n\n"
    "**Senior Performance Marketing Manager**\n\n"
    "## Berufserfahrung\n\n"
    "### Acme Corp | Berlin\n\n"
    "**Senior Manager** | *2019 – 2021*\n\n"
    "Dinge gebaut.\n"
)


def _profile() -> dict:
    return {
        "full_name": "Test Candidate",
        "headline": "Senior Performance Marketing Manager",
        "location": "Hamburg, Germany",
        "skills": ["Google Ads", "Programmatic Media Buying"],
        "positions": [
            {
                "title": "Senior Manager",
                "company": "Acme Corp",
                "start": "2019",
                "end": "2021",
                "description": "Built things.",
            }
        ],
    }


@pytest.fixture(autouse=True)
def _profile_and_cv(monkeypatch):
    monkeypatch.setattr("jobscout.draft.load_profile", _profile)
    monkeypatch.setattr(
        "jobscout.draft.load_cv_markdown",
        lambda language: _CV_BASE_DE if language.lower().startswith("de") else _CV_BASE_EN,
    )


def _listing(language: str = "en") -> Listing:
    return Listing(
        id="ulistid",
        source=Source.LINKEDIN,
        source_id="x",
        url="https://x",
        title="Performance Marketing Manager",
        description="Lead programmatic campaigns",
        language=language,
        raw={},
    )


@patch("jobscout.draft.update_listing_status")
@patch("jobscout.draft.write_draft")
@patch("jobscout.draft.call_text")
def test_draft_one_persists_and_updates_status(mock_call, mock_write, mock_update):
    base = _CV_BASE_EN
    mock_call.side_effect = ["cover letter body", base]
    mock_write.return_value = "draft-uuid"

    draft = draft_one(_listing())

    assert isinstance(draft, Draft)
    assert draft.listing_id == "ulistid"
    assert draft.body == "cover letter body"
    assert draft.adapted_cv == base
    mock_write.assert_called_once()
    mock_update.assert_called_once_with("ulistid", ListingStatus.DRAFTED)
    assert mock_call.call_count == 2


@patch("jobscout.draft.update_listing_status")
@patch("jobscout.draft.write_draft")
@patch("jobscout.draft.call_text")
def test_draft_one_raises_when_employer_header_drops(mock_call, mock_write, mock_update):
    mock_call.side_effect = ["cover letter body", "# Someone\n\nGeneric content with no facts.\n"]

    with pytest.raises(ValueError, match="broke fact preservation"):
        draft_one(_listing())

    mock_write.assert_not_called()
    mock_update.assert_not_called()


@patch("jobscout.draft.update_listing_status")
@patch("jobscout.draft.write_draft")
@patch("jobscout.draft.call_text")
def test_draft_one_german_listing_uses_german_cv(mock_call, mock_write, mock_update):
    base_de = _CV_BASE_DE
    mock_call.side_effect = ["Bewerbungstext", base_de]
    mock_write.return_value = "draft-uuid"

    draft = draft_one(_listing(language="de"))

    assert draft.language == "de"
    assert "Berufserfahrung" in draft.adapted_cv


def test_verify_cv_facts_finds_dropped_header():
    base = "# X\n\n## Work\n\n### Acme Corp | Berlin\n### Beta Ltd | Hamburg\n"
    adapted = "# X\n\n## Work\n\n### Acme Corp | Berlin\n"
    violations = _verify_cv_facts(base, adapted)
    assert any("Beta Ltd" in v for v in violations)


def test_verify_cv_facts_finds_dropped_year():
    base = "# X\n\n### Acme Corp | Berlin\n*2019 – 2020*\n"  # noqa: RUF001
    adapted = "# X\n\n### Acme Corp | Berlin\n*– 2020*\n"  # noqa: RUF001
    violations = _verify_cv_facts(base, adapted)
    assert any("dropped years" in v for v in violations)


def test_extract_contact_name_simple():
    text = "Some intro. Ansprechpartner: Stephan Domke. More text."
    assert _extract_contact_name(text) == "Stephan Domke"


def test_extract_contact_name_with_umlaut():
    text = "Kontakt\nAnsprechpartner: Jürgen Müller-Heinemann"
    assert _extract_contact_name(text) == "Jürgen Müller-Heinemann"


def test_extract_contact_name_absent():
    assert _extract_contact_name("no contact info here") == ""


def test_verify_cv_facts_clean_pass():
    base = "# X\n\n### Acme | Berlin\n*2019 – 2020*\n- bullet\n"  # noqa: RUF001
    adapted = "# X\n\n### Acme | Berlin\n*2019 – 2020*\n- bullet\n"  # noqa: RUF001
    assert _verify_cv_facts(base, adapted) == []


def test_proposal_prompt_includes_candidate_fields():
    listing = _listing()
    rendered = _build_proposal_prompt(_profile(), listing, "en", "")
    assert "{{" not in rendered
    assert "Test Candidate" in rendered
    assert "Senior Performance Marketing Manager" in rendered
    assert "Google Ads" in rendered
    assert "Acme Corp" in rendered


def test_cv_prompt_renders_without_unfilled_placeholders():
    rendered = _PROMPT_CV.replace("{{cv_base_markdown}}", "# Test\n\n## Work\n").replace(
        "{{listing_full}}", "title\n\ndesc"
    )
    assert "{{" not in rendered

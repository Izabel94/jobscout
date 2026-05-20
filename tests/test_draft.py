"""Phase 8 smoke tests — verify draft pipeline wiring without hitting an LLM."""

from unittest.mock import patch

import pytest

from jobscout.config_loader import load_cv_markdown
from jobscout.draft import _extract_contact_name, _verify_cv_facts, draft_one
from jobscout.models import Draft, Listing, ListingStatus, Source


def _listing(language: str = "en") -> Listing:
    return Listing(
        id="ulistid",
        source=Source.UPWORK,
        source_id="x",
        url="https://x",
        title="LangChain engineer",
        description="Build a production RAG pipeline",
        language=language,
        raw={},
    )


@patch("jobscout.draft.update_listing_status")
@patch("jobscout.draft.write_draft")
@patch("jobscout.draft.call_text")
def test_draft_one_persists_and_updates_status(mock_call, mock_write, mock_update):
    base = load_cv_markdown("en")
    # The "adapted" CV is the unchanged base — that's a valid surgical edit
    # (zero changes) and must always preserve facts.
    mock_call.side_effect = ["proposal body text", base]
    mock_write.return_value = "draft-uuid"

    draft = draft_one(_listing())

    assert isinstance(draft, Draft)
    assert draft.listing_id == "ulistid"
    assert draft.body == "proposal body text"
    assert draft.adapted_cv == base
    mock_write.assert_called_once()
    mock_update.assert_called_once_with("ulistid", ListingStatus.DRAFTED)
    assert mock_call.call_count == 2


@patch("jobscout.draft.update_listing_status")
@patch("jobscout.draft.write_draft")
@patch("jobscout.draft.call_text")
def test_draft_one_raises_when_employer_header_drops(mock_call, mock_write, mock_update):
    mock_call.side_effect = ["proposal body", "# Someone\n\nGeneric content with no facts.\n"]

    with pytest.raises(ValueError, match="broke fact preservation"):
        draft_one(_listing())

    mock_write.assert_not_called()
    mock_update.assert_not_called()


@patch("jobscout.draft.update_listing_status")
@patch("jobscout.draft.write_draft")
@patch("jobscout.draft.call_text")
def test_draft_one_german_listing_uses_german_cv(mock_call, mock_write, mock_update):
    base_de = load_cv_markdown("de")
    mock_call.side_effect = ["Bewerbung text", base_de]
    mock_write.return_value = "draft-uuid"

    draft = draft_one(_listing(language="de"))

    assert draft.language == "de"
    # Verify the German CV was loaded — it has the German section heading.
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


def test_proposal_prompt_renders_without_unfilled_placeholders():
    from jobscout.draft import _PROMPT_PROP, _case_studies, _profile_blurb

    profile = {
        "name": "Test",
        "target_rate_floor_eur_hr": 60,
        "required_skill_keywords": ["LangChain", "RAG"],
        "anchor_case_studies": [{"title": "T", "summary": "S"}],
    }
    rendered = (
        _PROMPT_PROP.replace("{{profile_blurb}}", _profile_blurb(profile))
        .replace("{{candidate_name}}", profile["name"])
        .replace("{{anchor_case_studies}}", _case_studies(profile))
        .replace("{{title}}", "title")
        .replace("{{description}}", "desc")
        .replace("{{language}}", "en")
        .replace("{{contact_name}}", "")
    )
    assert "{{" not in rendered


def test_cv_prompt_renders_without_unfilled_placeholders():
    from jobscout.draft import _PROMPT_CV

    rendered = _PROMPT_CV.replace("{{cv_base_markdown}}", "# Test\n\n## Work\n").replace(
        "{{listing_full}}", "title\n\ndesc"
    )
    assert "{{" not in rendered

"""Smoke tests for score.py — verify prompt rendering + main loop wiring without hitting an LLM."""

from unittest.mock import patch

from jobscout.models import ListingStatus
from jobscout.score import _build_score_prompt, main


def _profile() -> dict:
    return {
        "full_name": "Test Candidate",
        "headline": "Senior Performance Marketing Manager",
        "location": "Hamburg, Germany",
        "skills": ["Google Ads", "Programmatic Media Buying"],
        "positions": [
            {
                "title": "Senior Consultant",
                "company": "Acme Media",
                "start": "2023-01",
                "end": "present",
                "description": "Programmatic campaigns across Display, CTV, DOOH.",
            }
        ],
        "education": [{"degree": "B.Sc. Marketing", "school": "Uni Hamburg", "year": "2020"}],
    }


def test_build_score_prompt_includes_candidate_fields():
    listing = {
        "title": "Performance Marketing Manager",
        "description": "Lead programmatic campaigns",
        "language": "en",
    }
    rendered = _build_score_prompt(_profile(), listing)
    assert "{{" not in rendered, "all placeholders should be replaced"
    assert "Test Candidate" in rendered
    assert "Senior Performance Marketing Manager" in rendered
    assert "Google Ads" in rendered
    assert "Acme Media" in rendered
    assert "Performance Marketing Manager" in rendered  # listing title


def test_build_score_prompt_handles_minimal_profile():
    listing = {"title": "X", "description": "Y"}
    rendered = _build_score_prompt({"full_name": "X"}, listing)
    assert "{{" not in rendered


@patch("jobscout.score.call_json")
@patch("jobscout.score.list_unscored_new_listings")
@patch("jobscout.score.update_listing_status")
@patch("jobscout.score.load_profile")
def test_main_scores_and_updates(mock_profile, mock_update, mock_list, mock_call):
    mock_profile.return_value = _profile()
    mock_list.return_value = [
        {
            "id": "u1",
            "source": "linkedin",
            "source_id": "abc",
            "url": "https://x",
            "title": "Performance Marketing Manager",
            "description": "Programmatic campaigns",
            "raw": {},
        },
    ]
    mock_call.return_value = {"score": 82, "rationale": "good fit", "red_flags": []}
    main()
    mock_call.assert_called_once()
    mock_update.assert_called_once_with("u1", ListingStatus.SCORED, score=82, score_rationale="good fit")

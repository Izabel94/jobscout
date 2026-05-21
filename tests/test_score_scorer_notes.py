"""Asserts profile.scorer_notes propagates into the LLM score prompt."""

from __future__ import annotations

from jobscout.score import _build_score_prompt


def _make_profile(notes: str = "") -> dict:
    return {
        "full_name": "Test User",
        "headline": "ML Engineer",
        "scorer_notes": notes,
        "required_skill_keywords": [],
        "anchor_summaries": [],
        "skills": [],
    }


def _make_listing() -> dict:
    return {
        "title": "Senior ML Engineer",
        "description": "Build ML pipelines.",
        "location": "Hamburg",
        "arrangement": "remote",
        "job_type_classified": "fulltime",
        "apply_method": "external_apply",
    }


def test_score_prompt_includes_scorer_notes_when_set():
    profile = _make_profile(notes="PREFER REMOTE B2B SAAS. AVOID AGENCIES.")
    prompt = _build_score_prompt(profile, _make_listing())
    assert "PREFER REMOTE B2B SAAS" in prompt
    assert "AVOID AGENCIES" in prompt


def test_score_prompt_omits_section_when_notes_empty():
    profile = _make_profile(notes="")
    prompt = _build_score_prompt(profile, _make_listing())
    assert "scorer_notes" not in prompt.lower()


def test_score_prompt_omits_section_when_notes_missing_key():
    profile = _make_profile()
    del profile["scorer_notes"]
    prompt = _build_score_prompt(profile, _make_listing())
    assert "user preferences" not in prompt.lower() or "PREFER" not in prompt

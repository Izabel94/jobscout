"""Hits real Supabase. Requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
in env. Idempotent — cleans up by linkedin_url after each test."""

from __future__ import annotations

import os

import pytest

from jobscout.db import _client, get_profile, upsert_profile

TEST_LINKEDIN_URL = "https://www.linkedin.com/in/__jobscout_test_user__/"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    _client().table("profiles").delete().eq("linkedin_url", TEST_LINKEDIN_URL).execute()


@pytest.mark.skipif(not os.environ.get("SUPABASE_URL"), reason="needs supabase")
def test_upsert_and_get_profile():
    upsert_profile(
        {
            "full_name": "Test User",
            "linkedin_url": TEST_LINKEDIN_URL,
            "headline": "ML Engineer",
            "skills": ["Python", "PyTorch"],
            "required_skill_keywords": ["LLM", "RAG"],
            "title_denylist": ["WordPress"],
            "arrangement_preferences": ["remote", "hybrid"],
        }
    )
    p = get_profile(TEST_LINKEDIN_URL)
    assert p is not None
    assert p["full_name"] == "Test User"
    assert "Python" in p["skills"]
    assert "LLM" in p["required_skill_keywords"]


@pytest.mark.skipif(not os.environ.get("SUPABASE_URL"), reason="needs supabase")
def test_upsert_is_idempotent():
    """Calling upsert_profile twice with the same linkedin_url updates, not duplicates."""
    upsert_profile({"full_name": "A", "linkedin_url": TEST_LINKEDIN_URL})
    upsert_profile({"full_name": "B", "linkedin_url": TEST_LINKEDIN_URL})
    p = get_profile(TEST_LINKEDIN_URL)
    assert p["full_name"] == "B"


@pytest.mark.skipif(not os.environ.get("SUPABASE_URL"), reason="needs supabase")
def test_get_profile_returns_none_for_unknown():
    assert get_profile("https://www.linkedin.com/in/__never_exists__/") is None

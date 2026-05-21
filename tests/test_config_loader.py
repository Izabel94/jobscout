"""load_profile reads the single profiles row from Supabase. Cached per
process; cache invalidated by clear_profile_cache(). Test inserts a row,
reads, asserts shape, cleans up."""

from __future__ import annotations

import os

import pytest

from jobscout.config_loader import clear_profile_cache, load_profile
from jobscout.db import _client, upsert_profile

TEST_URL = "https://www.linkedin.com/in/__jobscout_test_user_config__/"


@pytest.fixture(autouse=True)
def _cleanup(monkeypatch):
    clear_profile_cache()
    monkeypatch.setenv("JOBSCOUT_PROFILE_LINKEDIN_URL", TEST_URL)
    yield
    _client().table("profiles").delete().eq("linkedin_url", TEST_URL).execute()
    clear_profile_cache()


@pytest.mark.skipif(not os.environ.get("SUPABASE_URL"), reason="needs supabase")
def test_load_profile_returns_db_row():
    upsert_profile(
        {
            "full_name": "Test User",
            "linkedin_url": TEST_URL,
            "required_skill_keywords": ["LLM"],
            "title_denylist": ["WordPress"],
            "arrangement_preferences": ["remote"],
        }
    )
    p = load_profile()
    assert p["full_name"] == "Test User"
    assert p["required_skill_keywords"] == ["LLM"]
    assert p["title_denylist"] == ["WordPress"]


@pytest.mark.skipif(not os.environ.get("SUPABASE_URL"), reason="needs supabase")
def test_load_profile_raises_when_no_row():
    # No upsert — load_profile should fail loudly, not return empty dict
    with pytest.raises(RuntimeError, match="No profiles row"):
        load_profile()


def test_load_profile_raises_when_env_unset(monkeypatch):
    monkeypatch.delenv("JOBSCOUT_PROFILE_LINKEDIN_URL", raising=False)
    clear_profile_cache()
    with pytest.raises(RuntimeError, match="JOBSCOUT_PROFILE_LINKEDIN_URL"):
        load_profile()

"""Tests the save path — given a pending_profile mutation, save_profile_changes
upserts to DB + clears cache. Streamlit session_state isn't directly testable;
save_profile_changes takes the dict as an arg so it's pure-function testable."""

from __future__ import annotations

import os

import pytest

from jobscout.db import _client, get_profile, upsert_profile
from jobscout.ui.settings import save_profile_changes

TEST_URL = "https://www.linkedin.com/in/__jobscout_settings_save_test__/"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    _client().table("profiles").delete().eq("linkedin_url", TEST_URL).execute()


@pytest.mark.skipif(not os.environ.get("SUPABASE_URL"), reason="needs supabase")
def test_save_profile_changes_writes_to_db_and_clears_cache():
    upsert_profile({
        "full_name": "Save Test",
        "linkedin_url": TEST_URL,
        "required_skill_keywords": ["A", "B"],
    })

    pending = {
        **(get_profile(TEST_URL) or {}),
        "required_skill_keywords": ["X", "Y", "Z"],
        "scorer_notes": "test notes",
    }
    save_profile_changes(pending)

    fresh = get_profile(TEST_URL)
    assert fresh["required_skill_keywords"] == ["X", "Y", "Z"]
    assert fresh["scorer_notes"] == "test notes"

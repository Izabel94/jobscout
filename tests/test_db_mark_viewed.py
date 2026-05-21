"""Hits real Supabase. Tests mark_listing_viewed idempotency + that
first_discovered_at is NOT clobbered by upsert."""

from __future__ import annotations

import os
import time

import pytest

from jobscout.db import _client, mark_listing_viewed, upsert_listing
from jobscout.models import (
    ApplyMethod,
    Arrangement,
    JobType,
    Listing,
    Source,
)

TEST_SOURCE_ID = "phase3-test-listing"


def _make_listing() -> Listing:
    return Listing(
        source=Source.LINKEDIN,
        source_id=TEST_SOURCE_ID,
        url="https://linkedin.com/jobs/view/test",
        title="Phase 3 Test Role",
        raw={},
        arrangement=Arrangement.REMOTE,
        job_type_classified=JobType.FULLTIME,
        apply_method=ApplyMethod.EXTERNAL_APPLY,
    )


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    _client().table("listings").delete().eq("source_id", TEST_SOURCE_ID).execute()


@pytest.mark.skipif(not os.environ.get("SUPABASE_URL"), reason="needs supabase")
def test_mark_listing_viewed_sets_viewed_at_once():
    upsert_listing(_make_listing())
    row = (
        _client().table("listings").select("id,viewed_at,first_discovered_at")
        .eq("source_id", TEST_SOURCE_ID).execute().data[0]
    )
    assert row["viewed_at"] is None
    assert row["first_discovered_at"] is not None
    listing_id = row["id"]

    mark_listing_viewed(listing_id)
    row = (
        _client().table("listings").select("viewed_at,first_discovered_at")
        .eq("id", listing_id).execute().data[0]
    )
    assert row["viewed_at"] is not None
    first_viewed_at = row["viewed_at"]

    time.sleep(0.05)
    mark_listing_viewed(listing_id)  # idempotent — should NOT overwrite
    row = (
        _client().table("listings").select("viewed_at")
        .eq("id", listing_id).execute().data[0]
    )
    assert row["viewed_at"] == first_viewed_at


@pytest.mark.skipif(not os.environ.get("SUPABASE_URL"), reason="needs supabase")
def test_upsert_does_not_clobber_first_discovered_at():
    upsert_listing(_make_listing())
    row = (
        _client().table("listings").select("id,first_discovered_at")
        .eq("source_id", TEST_SOURCE_ID).execute().data[0]
    )
    original = row["first_discovered_at"]

    time.sleep(0.05)
    upsert_listing(_make_listing())  # re-discovery
    row = (
        _client().table("listings").select("first_discovered_at")
        .eq("source_id", TEST_SOURCE_ID).execute().data[0]
    )
    assert row["first_discovered_at"] == original, "re-upsert clobbered first_discovered_at"

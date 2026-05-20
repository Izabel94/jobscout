"""Tests for jobscout.apply helpers (submissions_today daily-cap accounting)."""

from unittest.mock import patch

from jobscout.apply import submissions_today


@patch("jobscout.apply._client")
def test_submissions_today_counts_only_matching_source(mock_client):
    chain = mock_client.return_value.table.return_value
    chain.select.return_value.gte.return_value.execute.return_value.data = [
        {"id": "s1", "submitted_at": "now", "listings": {"source": "freelancermap"}},
        {"id": "s2", "submitted_at": "now", "listings": {"source": "linkedin"}},
        {"id": "s3", "submitted_at": "now", "listings": {"source": "freelancermap"}},
    ]
    assert submissions_today("freelancermap") == 2
    assert submissions_today("linkedin") == 1
    assert submissions_today("upwork") == 0


@patch("jobscout.apply._client")
def test_submissions_today_handles_missing_listings_join(mock_client):
    chain = mock_client.return_value.table.return_value
    # If the join returns null, listings is None or absent — must not crash.
    chain.select.return_value.gte.return_value.execute.return_value.data = [
        {"id": "s1", "submitted_at": "now", "listings": None},
        {"id": "s2", "submitted_at": "now"},
    ]
    assert submissions_today("freelancermap") == 0


@patch("jobscout.apply._client")
def test_submissions_today_empty_data(mock_client):
    chain = mock_client.return_value.table.return_value
    chain.select.return_value.gte.return_value.execute.return_value.data = []
    assert submissions_today("freelancermap") == 0

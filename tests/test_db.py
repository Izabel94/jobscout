from unittest.mock import MagicMock, patch

from jobscout.db import (
    claim_one_pending_apply_request,
    get_latest_draft_for_listing,
    list_by_status,
    list_pipeline_listings,
    list_source_runs,
    list_unscored_new_listings,
    upsert_listing,
)
from jobscout.models import Listing, ListingStatus, Source


@patch("jobscout.db._client")
def test_upsert_listing_calls_supabase(mock_client):
    mock_table = MagicMock()
    mock_client.return_value.table.return_value = mock_table
    mock_table.upsert.return_value.execute.return_value.data = [{"id": "uuid"}]
    listing = Listing(source=Source.UPWORK, source_id="abc", url="https://x", title="t", raw={})
    assert upsert_listing(listing) == "uuid"
    mock_client.return_value.table.assert_called_with("listings")


@patch("jobscout.db._client")
def test_list_by_status_filters_and_orders(mock_client):
    chain = mock_client.return_value.table.return_value
    chain.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
        {"id": "u1", "status": "new"},
    ]
    assert list_by_status(ListingStatus.NEW) == [{"id": "u1", "status": "new"}]
    chain.select.return_value.eq.assert_called_with("status", "new")


@patch("jobscout.db._client")
def test_list_unscored_new_listings_filters_status_and_null_score(mock_client):
    chain = mock_client.return_value.table.return_value
    chain.select.return_value.eq.return_value.is_.return_value.execute.return_value.data = [
        {"id": "u2", "status": "new", "score": None},
    ]
    assert list_unscored_new_listings() == [{"id": "u2", "status": "new", "score": None}]
    chain.select.return_value.eq.assert_called_with("status", "new")
    chain.select.return_value.eq.return_value.is_.assert_called_with("score", "null")


@patch("jobscout.db._client")
def test_list_pipeline_listings_filters_in_and_orders_and_limits(mock_client):
    chain = mock_client.return_value.table.return_value
    in_chain = chain.select.return_value.in_.return_value.order.return_value.limit.return_value
    in_chain.execute.return_value.data = [{"id": "u3", "status": "scored", "score": 80}]
    out = list_pipeline_listings([ListingStatus.SCORED, ListingStatus.DRAFTED], limit=50)
    assert out == [{"id": "u3", "status": "scored", "score": 80}]
    mock_client.return_value.table.assert_called_with("listings")
    chain.select.return_value.in_.assert_called_with("status", ["scored", "drafted"])
    chain.select.return_value.in_.return_value.order.assert_called_with("score", desc=True, nullsfirst=False)
    chain.select.return_value.in_.return_value.order.return_value.limit.assert_called_with(50)


@patch("jobscout.db._client")
def test_list_pipeline_listings_empty_statuses_returns_empty(mock_client):
    assert list_pipeline_listings([]) == []
    mock_client.return_value.table.assert_not_called()


@patch("jobscout.db._client")
def test_list_source_runs_orders_desc_and_limits(mock_client):
    chain = mock_client.return_value.table.return_value
    chain.select.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"id": 1, "source": "upwork"},
    ]
    assert list_source_runs(limit=10) == [{"id": 1, "source": "upwork"}]
    mock_client.return_value.table.assert_called_with("source_runs")
    chain.select.return_value.order.assert_called_with("started_at", desc=True)
    chain.select.return_value.order.return_value.limit.assert_called_with(10)


@patch("jobscout.db._client")
def test_get_latest_draft_returns_first_row(mock_client):
    chain = mock_client.return_value.table.return_value
    pipe = chain.select.return_value.eq.return_value.order.return_value.limit.return_value
    pipe.execute.return_value.data = [{"id": "d1", "listing_id": "l1", "body": "..."}]
    assert get_latest_draft_for_listing("l1") == {"id": "d1", "listing_id": "l1", "body": "..."}
    mock_client.return_value.table.assert_called_with("drafts")
    chain.select.return_value.eq.assert_called_with("listing_id", "l1")
    chain.select.return_value.eq.return_value.order.assert_called_with("created_at", desc=True)
    chain.select.return_value.eq.return_value.order.return_value.limit.assert_called_with(1)


@patch("jobscout.db._client")
def test_get_latest_draft_returns_none_when_no_rows(mock_client):
    chain = mock_client.return_value.table.return_value
    chain.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
    assert get_latest_draft_for_listing("nope") is None


@patch("jobscout.db._client")
def test_insert_apply_request_writes_row(mock_client):
    mock_client.return_value.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "req-123", "listing_id": "list-abc", "source": "upwork", "status": "pending"}
    ]
    from jobscout.db import insert_apply_request

    request_id = insert_apply_request(listing_id="list-abc", source="upwork")

    assert request_id == "req-123"
    mock_client.return_value.table.assert_called_with("apply_requests")
    insert_call = mock_client.return_value.table.return_value.insert.call_args[0][0]
    assert insert_call["listing_id"] == "list-abc"
    assert insert_call["source"] == "upwork"
    assert insert_call["status"] == "pending"


@patch("jobscout.db._client")
def test_claim_one_pending_returns_claimed_row(mock_client):
    sel = mock_client.return_value.table.return_value.select.return_value
    sel.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"id": "req-1", "listing_id": "list-1", "source": "upwork", "status": "pending"}
    ]
    upd = mock_client.return_value.table.return_value.update.return_value
    upd.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "req-1", "status": "processing"}]

    row = claim_one_pending_apply_request()

    assert row is not None
    assert row["id"] == "req-1"


@patch("jobscout.db._client")
def test_claim_one_pending_returns_none_when_queue_empty(mock_client):
    sel = mock_client.return_value.table.return_value.select.return_value
    sel.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []

    assert claim_one_pending_apply_request() is None


@patch("jobscout.db._client")
def test_claim_one_pending_returns_none_when_another_worker_won(mock_client):
    sel = mock_client.return_value.table.return_value.select.return_value
    sel.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"id": "req-1", "listing_id": "list-1", "source": "upwork", "status": "pending"}
    ]
    upd = mock_client.return_value.table.return_value.update.return_value
    upd.eq.return_value.eq.return_value.execute.return_value.data = []

    assert claim_one_pending_apply_request() is None


@patch("jobscout.db._client")
def test_mark_apply_request_done_writes_completion_fields(mock_client):
    from jobscout.db import mark_apply_request_done

    mark_apply_request_done("req-1", executed_draft_id="draft-1", notes="filled 8/13 fields")

    upd = mock_client.return_value.table.return_value.update.call_args[0][0]
    assert upd["status"] == "done"
    assert upd["executed_draft_id"] == "draft-1"
    assert upd["notes"] == "filled 8/13 fields"
    assert "completed_at" in upd


@patch("jobscout.db._client")
def test_mark_apply_request_failed_writes_error_and_notes(mock_client):
    from jobscout.db import mark_apply_request_failed

    mark_apply_request_failed("req-1", error="Chrome not running", notes="cdp probe failed")

    upd = mock_client.return_value.table.return_value.update.call_args[0][0]
    assert upd["status"] == "failed"
    assert upd["error"] == "Chrome not running"
    assert upd["notes"] == "cdp probe failed"
    assert "completed_at" in upd


@patch("jobscout.db._client")
def test_mark_apply_request_failed_truncates_long_error_and_notes(mock_client):
    from jobscout.db import mark_apply_request_failed

    long_error = "x" * 3000
    long_notes = "y" * 3000
    mark_apply_request_failed("req-1", error=long_error, notes=long_notes)

    upd = mock_client.return_value.table.return_value.update.call_args[0][0]
    assert len(upd["error"]) == 2000
    assert upd["error"] == "x" * 2000
    assert len(upd["notes"]) == 2000
    assert upd["notes"] == "y" * 2000


@patch("jobscout.db._client")
def test_recover_stale_apply_claims_resets_old_processing_rows(mock_client):
    upd_chain = mock_client.return_value.table.return_value.update.return_value
    upd_chain.eq.return_value.lt.return_value.execute.return_value.data = [
        {"id": "req-1"},
        {"id": "req-2"},
    ]
    from jobscout.db import recover_stale_apply_claims

    count = recover_stale_apply_claims(stale_after_minutes=30)

    assert count == 2
    upd_payload = mock_client.return_value.table.return_value.update.call_args[0][0]
    assert upd_payload["status"] == "pending"
    assert upd_payload["claimed_at"] is None
    # The status filter must target rows currently in 'processing'
    upd_chain.eq.assert_called_with("status", "processing")
    # The claimed_at filter must use the cutoff (less-than)
    lt_args = upd_chain.eq.return_value.lt.call_args
    assert lt_args[0][0] == "claimed_at"
    # Cutoff is a UTC ISO string; just verify it's a non-empty str
    assert isinstance(lt_args[0][1], str) and lt_args[0][1].endswith("+00:00")


@patch("jobscout.db._client")
def test_list_apply_requests_returns_recent_rows(mock_client):
    sel = mock_client.return_value.table.return_value.select.return_value
    sel.order.return_value.limit.return_value.execute.return_value.data = [
        {"id": "req-1", "status": "done"},
        {"id": "req-2", "status": "pending"},
    ]
    from jobscout.db import list_apply_requests

    rows = list_apply_requests(limit=10)

    assert len(rows) == 2
    sel.order.assert_called_with("requested_at", desc=True)
    sel.order.return_value.limit.assert_called_with(10)

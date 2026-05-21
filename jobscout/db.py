import os
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any, cast

from jobscout.models import Draft, Listing, ListingStatus
from supabase import Client, create_client


@lru_cache(maxsize=1)
def _client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_ANON_KEY"]
    return create_client(url, key)


def upsert_listing(listing: Listing) -> str:
    """Workflow fields (status, score, *_rationale, spam_score) are excluded so re-discovery doesn't clobber user progress."""
    payload = listing.model_dump(
        mode="json",
        exclude={"id", "status", "score", "score_rationale", "spam_score"},
    )
    payload["discovered_at"] = payload.get("discovered_at") or datetime.now().isoformat()
    res = _client().table("listings").upsert(payload, on_conflict="source,source_id").execute()
    row = cast(dict[str, Any], res.data[0])
    return str(row["id"])


def update_listing_status(
    listing_id: str,
    status: ListingStatus,
    score: int | None = None,
    score_rationale: str | None = None,
    spam_score: int | None = None,
) -> None:
    patch: dict[str, Any] = {"status": status.value}
    if score is not None:
        patch["score"] = score
    if score_rationale is not None:
        patch["score_rationale"] = score_rationale
    if spam_score is not None:
        patch["spam_score"] = spam_score
    _client().table("listings").update(patch).eq("id", listing_id).execute()


def list_by_status(status: ListingStatus) -> list[dict[str, Any]]:
    res = (
        _client()
        .table("listings")
        .select("*")
        .eq("status", status.value)
        .order("score", desc=True, nullsfirst=False)
        .execute()
    )
    return cast(list[dict[str, Any]], res.data)


def list_unscored_new_listings() -> list[dict[str, Any]]:
    """Listings awaiting LLM scoring: status='new' AND score IS NULL."""
    res = _client().table("listings").select("*").eq("status", ListingStatus.NEW.value).is_("score", "null").execute()
    return cast(list[dict[str, Any]], res.data)


def write_draft(d: Draft) -> str:
    payload = d.model_dump(mode="json", exclude={"id"})
    res = _client().table("drafts").insert(payload).execute()
    row = cast(dict[str, Any], res.data[0])
    return str(row["id"])


def record_submission(listing_id: str, draft_id: str | None, channel: str, notes: str | None = None) -> str:
    res = (
        _client()
        .table("submissions")
        .insert({"listing_id": listing_id, "draft_id": draft_id, "channel": channel, "notes": notes})
        .execute()
    )
    row = cast(dict[str, Any], res.data[0])
    return str(row["id"])


def log_source_run(source: str, listings_found: int, listings_new: int, error: str | None = None) -> None:
    _client().table("source_runs").insert(
        {
            "source": source,
            "finished_at": datetime.now().isoformat(),
            "listings_found": listings_found,
            "listings_new": listings_new,
            "error": error,
        }
    ).execute()


def list_pipeline_listings(statuses: list[ListingStatus], limit: int = 100) -> list[dict[str, Any]]:
    """Listings in any of the given statuses, ordered by score desc (nulls last)."""
    if not statuses:
        return []
    status_values = [s.value for s in statuses]
    res = (
        _client()
        .table("listings")
        .select("*")
        .in_("status", status_values)
        .order("score", desc=True, nullsfirst=False)
        .limit(limit)
        .execute()
    )
    return cast(list[dict[str, Any]], res.data)


def list_source_runs(limit: int = 40) -> list[dict[str, Any]]:
    """Most recent source_runs, descending by start time."""
    res = _client().table("source_runs").select("*").order("started_at", desc=True).limit(limit).execute()
    return cast(list[dict[str, Any]], res.data)


def get_profile(linkedin_url: str) -> dict[str, Any] | None:
    """Returns the single profile row matching linkedin_url, or None."""
    r = _client().table("profiles").select("*").eq("linkedin_url", linkedin_url).execute()
    rows = r.data or []
    return rows[0] if rows else None


def upsert_profile(profile: dict[str, Any]) -> None:
    """Insert or update by linkedin_url. Server-side timestamps."""
    payload = dict(profile)
    payload.pop("id", None)
    payload.pop("updated_at", None)
    _client().table("profiles").upsert(payload, on_conflict="linkedin_url").execute()


def get_listing_by_id(listing_id: str) -> dict[str, Any] | None:
    """Return one listing row by primary key, or None if not found."""
    res = _client().table("listings").select("*").eq("id", listing_id).limit(1).execute()
    if not res.data:
        return None
    return cast(dict[str, Any], res.data[0])


def get_latest_draft_for_listing(listing_id: str) -> dict[str, Any] | None:
    """Most recent draft for a listing, or None if no draft exists."""
    res = (
        _client()
        .table("drafts")
        .select("*")
        .eq("listing_id", listing_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = cast(list[dict[str, Any]], res.data)
    return rows[0] if rows else None


def insert_apply_request(*, listing_id: str, source: str) -> str:
    """Source is copied from the listing at insert time so the worker doesn't have to re-fetch it."""
    res = (
        _client()
        .table("apply_requests")
        .insert({"listing_id": listing_id, "source": source, "status": "pending"})
        .execute()
    )
    return cast(str, res.data[0]["id"])


def claim_one_pending_apply_request() -> dict[str, Any] | None:
    """Atomically claim the oldest pending row via two-step optimistic concurrency (Supabase REST has no RETURNING). Returns None if another worker won the race."""
    client = _client()
    res = client.table("apply_requests").select("*").eq("status", "pending").order("requested_at").limit(1).execute()
    if not res.data:
        return None
    candidate = res.data[0]
    upd = (
        client.table("apply_requests")
        .update({"status": "processing", "claimed_at": "now()"})
        .eq("id", candidate["id"])
        .eq("status", "pending")
        .execute()
    )
    if not upd.data:
        return None
    return cast(dict[str, Any], candidate)


def mark_apply_request_done(
    request_id: str, *, executed_draft_id: str | None, notes: str | None = None
) -> None:
    """Transition an apply_request from 'processing' to 'done'."""
    payload: dict[str, Any] = {
        "status": "done",
        "completed_at": "now()",
        "executed_draft_id": executed_draft_id,
    }
    if notes is not None:
        payload["notes"] = notes
    _client().table("apply_requests").update(payload).eq("id", request_id).execute()


def mark_apply_request_failed(
    request_id: str, *, error: str, notes: str | None = None
) -> None:
    """Transition an apply_request from 'processing' to 'failed'."""
    payload: dict[str, Any] = {
        "status": "failed",
        "completed_at": "now()",
        "error": error[:2000],  # cap so a stack trace doesn't blow up the row
    }
    if notes is not None:
        payload["notes"] = notes[:2000]
    _client().table("apply_requests").update(payload).eq("id", request_id).execute()


def recover_stale_apply_claims(*, stale_after_minutes: int = 30) -> int:
    """Reset rows stuck in 'processing' back to 'pending'. Covers worker crashes mid-apply."""
    cutoff = (datetime.now(tz=UTC) - timedelta(minutes=stale_after_minutes)).isoformat()
    res = (
        _client()
        .table("apply_requests")
        .update({"status": "pending", "claimed_at": None})
        .eq("status", "processing")
        .lt("claimed_at", cutoff)
        .execute()
    )
    return len(res.data or [])


def list_apply_requests(*, limit: int = 50) -> list[dict[str, Any]]:
    """Most recent apply_requests, newest first."""
    res = (
        _client()
        .table("apply_requests")
        .select("*")
        .order("requested_at", desc=True)
        .limit(limit)
        .execute()
    )
    return cast(list[dict[str, Any]], res.data or [])

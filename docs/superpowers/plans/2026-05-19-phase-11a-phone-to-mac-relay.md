# Phase 11a — Phone-to-Mac Apply Relay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let user triage and queue auto-apply requests from her phone via a deployed Streamlit dashboard; a launchd-scheduled worker on her Mac picks up queued requests and runs the apply flow locally where her CDP Chrome lives.

**Architecture:** Deployed Streamlit (Streamlit Cloud free + Google OIDC) inserts rows into a new `apply_requests` table on cloud Supabase. A local launchd job polls the table every 5 minutes, claims one row atomically, fetches the latest draft, renders the CV PDF locally, dispatches to the existing apply modules, and marks the row done/failed.

**Tech Stack:** Python 3.13, Streamlit 1.32+, Supabase (cloud + local), Playwright (already used), macOS launchd, Google OIDC.

**Source spec:** `docs/superpowers/specs/2026-05-19-phase-11a-phone-to-mac-relay-design.md`

---

## File Structure

**Create:**
- `supabase/migrations/20260519120000_apply_requests.sql` — schema for the new queue table
- `sidegig/apply/worker.py` — worker module; CLI via `python -m sidegig.apply.worker`
- `tests/test_apply_worker.py` — unit tests for worker dispatch + claim semantics
- `scripts/apply-worker-local.sh` — bash wrapper invoked by launchd; pre-flight + notification on failure
- `scripts/com.sidegig.apply-worker.plist` — launchd job (every 5 min)
- `docs/phase11a-setup.md` — Google OAuth + Streamlit Cloud + launchd install runbook

**Modify:**
- `sidegig/db.py` — add 6 queue helpers (`insert_apply_request`, `list_apply_requests`, `claim_one_pending_apply_request`, `mark_apply_request_done`, `mark_apply_request_failed`, `recover_stale_apply_claims`)
- `sidegig/ui/app.py` — `SIDEGIG_DEPLOYED` env gate; `st.login()` block when deployed; auto-apply buttons swap to "Queue auto-apply on Mac" when deployed; new "Apply queue" panel
- `tests/test_db.py` — tests for the 6 new helpers

---

### Task 1: Schema migration for `apply_requests`

**Files:**
- Create: `supabase/migrations/20260519120000_apply_requests.sql`

- [ ] **Step 1: Write the migration SQL**

Create `supabase/migrations/20260519120000_apply_requests.sql` with this exact content:

```sql
create table apply_requests (
  id                 uuid primary key default gen_random_uuid(),
  listing_id         uuid not null references listings(id) on delete cascade,
  source             text not null,
  status             text not null default 'pending',
  error              text,
  requested_at       timestamptz not null default now(),
  claimed_at         timestamptz,
  completed_at       timestamptz,
  executed_draft_id  uuid references drafts(id),
  notes              text
);
create index on apply_requests (status, requested_at);
```

- [ ] **Step 2: Apply the migration to local Supabase**

Run from project root:

```bash
supabase db reset --local --no-seed 2>/dev/null || supabase db push --local
```

(`db reset` rebuilds from migrations; if that's too destructive locally, paste the SQL into the local SQL editor at `http://localhost:54323`.)

- [ ] **Step 3: Apply the migration to cloud Supabase**

Open the cloud SQL editor at:
```
https://supabase.com/dashboard/project/mrqsvbiarormusmgxzrm/sql/new
```
Paste the migration SQL from Step 1 and click Run. Expected: "Success. No rows returned."

- [ ] **Step 4: Verify the table exists in both DBs**

```bash
PYTHONPATH=. poetry run dotenv run -- python -c "
from sidegig.db import _client
c = _client()
res = c.table('apply_requests').select('*', count='exact', head=True).execute()
print(f'apply_requests rows: {res.count}')
"
```

Expected: `apply_requests rows: 0` (no error).

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/20260519120000_apply_requests.sql
git commit -m "feat(db): add apply_requests table for phone-to-Mac relay queue"
```

---

### Task 2: DB helper — `insert_apply_request`

**Files:**
- Modify: `sidegig/db.py` (append new function)
- Modify: `tests/test_db.py` (append new tests)

- [ ] **Step 1: Write failing test**

Append to `tests/test_db.py` (inside the existing test functions area, following the style of `test_upsert_listing_calls_supabase`):

```python
def test_insert_apply_request_writes_row(mock_client):
    mock_client.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "req-123", "listing_id": "list-abc", "source": "upwork", "status": "pending"}
    ]
    from sidegig.db import insert_apply_request

    request_id = insert_apply_request(listing_id="list-abc", source="upwork")

    assert request_id == "req-123"
    mock_client.table.assert_called_with("apply_requests")
    insert_call = mock_client.table.return_value.insert.call_args[0][0]
    assert insert_call["listing_id"] == "list-abc"
    assert insert_call["source"] == "upwork"
    assert insert_call["status"] == "pending"
```

- [ ] **Step 2: Run test, verify it fails**

```bash
poetry run pytest tests/test_db.py::test_insert_apply_request_writes_row -v
```

Expected: `ImportError: cannot import name 'insert_apply_request' from 'sidegig.db'`

- [ ] **Step 3: Implement `insert_apply_request`**

Append to `sidegig/db.py` (after `get_latest_draft_for_listing`):

```python
def insert_apply_request(*, listing_id: str, source: str) -> str:
    """Insert a new pending apply_request and return its id.

    Called from the deployed Streamlit when the user clicks "Queue
    auto-apply on Mac". Source is copied from the listing at insert
    time so the worker doesn't have to re-fetch it.
    """
    res = (
        _client()
        .table("apply_requests")
        .insert({"listing_id": listing_id, "source": source, "status": "pending"})
        .execute()
    )
    return cast(str, res.data[0]["id"])
```

- [ ] **Step 4: Run test, verify it passes**

```bash
poetry run pytest tests/test_db.py::test_insert_apply_request_writes_row -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sidegig/db.py tests/test_db.py
git commit -m "feat(db): insert_apply_request helper for queue inserts"
```

---

### Task 3: DB helper — `claim_one_pending_apply_request` (atomic claim)

**Files:**
- Modify: `sidegig/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_db.py`:

```python
def test_claim_one_pending_returns_claimed_row(mock_client):
    # Two-step claim: select oldest pending, then conditional update.
    sel = mock_client.table.return_value.select.return_value
    sel.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"id": "req-1", "listing_id": "list-1", "source": "upwork", "status": "pending"}
    ]
    upd = mock_client.table.return_value.update.return_value
    upd.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "req-1", "status": "processing"}
    ]
    from sidegig.db import claim_one_pending_apply_request

    row = claim_one_pending_apply_request()

    assert row is not None
    assert row["id"] == "req-1"


def test_claim_one_pending_returns_none_when_queue_empty(mock_client):
    sel = mock_client.table.return_value.select.return_value
    sel.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
    from sidegig.db import claim_one_pending_apply_request

    assert claim_one_pending_apply_request() is None


def test_claim_one_pending_returns_none_when_another_worker_won(mock_client):
    # Select returns a row, but update finds 0 rows (status changed under us).
    sel = mock_client.table.return_value.select.return_value
    sel.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"id": "req-1", "listing_id": "list-1", "source": "upwork", "status": "pending"}
    ]
    upd = mock_client.table.return_value.update.return_value
    upd.eq.return_value.eq.return_value.execute.return_value.data = []
    from sidegig.db import claim_one_pending_apply_request

    assert claim_one_pending_apply_request() is None
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
poetry run pytest tests/test_db.py -k claim_one_pending -v
```

Expected: 3 failures (ImportError).

- [ ] **Step 3: Implement `claim_one_pending_apply_request`**

Append to `sidegig/db.py`:

```python
def claim_one_pending_apply_request() -> dict[str, Any] | None:
    """Atomically claim the oldest pending apply_request.

    Two-step optimistic concurrency (Supabase REST has no RETURNING):
      1. Read the oldest pending row.
      2. Conditional update WHERE id=X AND status='pending'.
    If the update affects 0 rows, another worker grabbed it — return None
    so the caller doesn't re-process a stolen row. Caller can re-invoke
    to try again.
    """
    client = _client()
    res = (
        client.table("apply_requests")
        .select("*")
        .eq("status", "pending")
        .order("requested_at")
        .limit(1)
        .execute()
    )
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
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
poetry run pytest tests/test_db.py -k claim_one_pending -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add sidegig/db.py tests/test_db.py
git commit -m "feat(db): claim_one_pending_apply_request with optimistic concurrency"
```

---

### Task 4: DB helpers — `mark_apply_request_done` + `mark_apply_request_failed`

**Files:**
- Modify: `sidegig/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_db.py`:

```python
def test_mark_apply_request_done_writes_completion_fields(mock_client):
    from sidegig.db import mark_apply_request_done

    mark_apply_request_done("req-1", executed_draft_id="draft-1", notes="filled 8/13 fields")

    upd = mock_client.table.return_value.update.call_args[0][0]
    assert upd["status"] == "done"
    assert upd["executed_draft_id"] == "draft-1"
    assert upd["notes"] == "filled 8/13 fields"
    assert "completed_at" in upd


def test_mark_apply_request_failed_writes_error_and_notes(mock_client):
    from sidegig.db import mark_apply_request_failed

    mark_apply_request_failed("req-1", error="Chrome not running", notes="cdp probe failed")

    upd = mock_client.table.return_value.update.call_args[0][0]
    assert upd["status"] == "failed"
    assert upd["error"] == "Chrome not running"
    assert upd["notes"] == "cdp probe failed"
    assert "completed_at" in upd
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
poetry run pytest tests/test_db.py -k mark_apply_request -v
```

Expected: 2 failures (ImportError).

- [ ] **Step 3: Implement both functions**

Append to `sidegig/db.py`:

```python
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
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
poetry run pytest tests/test_db.py -k mark_apply_request -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add sidegig/db.py tests/test_db.py
git commit -m "feat(db): mark_apply_request_done / _failed helpers"
```

---

### Task 5: DB helpers — `recover_stale_apply_claims` + `list_apply_requests`

**Files:**
- Modify: `sidegig/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_db.py`:

```python
def test_recover_stale_apply_claims_resets_old_processing_rows(mock_client):
    upd = mock_client.table.return_value.update.return_value
    upd.eq.return_value.lt.return_value.execute.return_value.data = [
        {"id": "req-1"},
        {"id": "req-2"},
    ]
    from sidegig.db import recover_stale_apply_claims

    count = recover_stale_apply_claims(stale_after_minutes=30)

    assert count == 2
    upd_payload = mock_client.table.return_value.update.call_args[0][0]
    assert upd_payload["status"] == "pending"
    assert upd_payload["claimed_at"] is None


def test_list_apply_requests_returns_recent_rows(mock_client):
    sel = mock_client.table.return_value.select.return_value
    sel.order.return_value.limit.return_value.execute.return_value.data = [
        {"id": "req-1", "status": "done"},
        {"id": "req-2", "status": "pending"},
    ]
    from sidegig.db import list_apply_requests

    rows = list_apply_requests(limit=10)

    assert len(rows) == 2
    sel.order.assert_called_with("requested_at", desc=True)
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
poetry run pytest tests/test_db.py -k "recover_stale_apply_claims or list_apply_requests" -v
```

Expected: 2 failures (ImportError).

- [ ] **Step 3: Implement both functions**

Append to `sidegig/db.py`:

```python
def recover_stale_apply_claims(*, stale_after_minutes: int = 30) -> int:
    """Reset any apply_request stuck in 'processing' for too long back to 'pending'.

    Run at the top of each worker invocation. Covers the case where a
    previous worker crashed mid-apply and left the row claimed.
    """
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(tz=timezone.utc) - timedelta(minutes=stale_after_minutes)).isoformat()
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
    """Return the most recent apply_requests (any status), newest first.

    Used by the Streamlit dashboard's queue-status panel.
    """
    res = (
        _client()
        .table("apply_requests")
        .select("*")
        .order("requested_at", desc=True)
        .limit(limit)
        .execute()
    )
    return cast(list[dict[str, Any]], res.data or [])
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
poetry run pytest tests/test_db.py -k "recover_stale_apply_claims or list_apply_requests" -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add sidegig/db.py tests/test_db.py
git commit -m "feat(db): recover_stale_apply_claims + list_apply_requests"
```

---

### Task 6: Worker module — dispatch logic

**Files:**
- Create: `sidegig/apply/worker.py`
- Create: `tests/test_apply_worker.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_apply_worker.py`:

```python
"""Tests for sidegig.apply.worker dispatch logic."""

from pathlib import Path
from unittest.mock import MagicMock, patch


def test_process_one_dispatches_upwork():
    row = {
        "id": "req-1",
        "listing_id": "list-1",
        "source": "upwork",
    }
    listing = {"id": "list-1", "url": "https://upwork.com/jobs/~abc", "title": "Test", "description": "desc"}
    draft = {"id": "draft-1", "body": "proposal text", "adapted_cv": "# CV"}

    with (
        patch("sidegig.apply.worker._fetch_listing", return_value=listing),
        patch("sidegig.apply.worker._fetch_latest_draft", return_value=draft),
        patch("sidegig.apply.worker._render_cv_pdf", return_value=Path("/tmp/cv.pdf")),
        patch("sidegig.apply.upwork.apply") as upwork_apply,
        patch("sidegig.apply.worker.mark_apply_request_done") as mark_done,
    ):
        from sidegig.apply.worker import process_one

        process_one(row)

        upwork_apply.assert_called_once()
        kwargs = upwork_apply.call_args.kwargs or {}
        args = upwork_apply.call_args.args
        # Either positional or kwargs — be tolerant
        assert "proposal text" in (kwargs.get("proposal") or args[1])
        mark_done.assert_called_once_with("req-1", executed_draft_id="draft-1", notes=None)


def test_process_one_dispatches_external_ats_for_bundesagentur():
    row = {"id": "req-2", "listing_id": "list-2", "source": "bundesagentur"}
    listing = {
        "id": "list-2",
        "url": "https://arbeitsagentur.de/...",
        "title": "AI",
        "description": "desc",
        "raw": {"externeUrl": "https://employer.example/apply"},
    }
    draft = {"id": "draft-2", "body": "proposal", "adapted_cv": "# CV"}

    with (
        patch("sidegig.apply.worker._fetch_listing", return_value=listing),
        patch("sidegig.apply.worker._fetch_latest_draft", return_value=draft),
        patch("sidegig.apply.worker._render_cv_pdf", return_value=Path("/tmp/cv.pdf")),
        patch("sidegig.apply.external_ats.apply") as ext_apply,
        patch("sidegig.apply.worker.mark_apply_request_done"),
    ):
        from sidegig.apply.worker import process_one

        process_one(row)

        ext_apply.assert_called_once()
        # External ATS uses externeUrl when present
        kwargs = ext_apply.call_args.kwargs
        assert kwargs["ats_url"] == "https://employer.example/apply"


def test_process_one_marks_failed_on_exception():
    row = {"id": "req-3", "listing_id": "list-3", "source": "upwork"}

    with (
        patch("sidegig.apply.worker._fetch_listing", side_effect=RuntimeError("boom")),
        patch("sidegig.apply.worker.mark_apply_request_failed") as mark_failed,
    ):
        from sidegig.apply.worker import process_one

        process_one(row)

        mark_failed.assert_called_once()
        assert "boom" in mark_failed.call_args.kwargs["error"]
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
poetry run pytest tests/test_apply_worker.py -v
```

Expected: 3 failures (ModuleNotFoundError: sidegig.apply.worker).

- [ ] **Step 3: Implement the worker module**

Create `sidegig/apply/worker.py`:

```python
"""Apply-queue worker — picks up pending apply_requests rows and runs
the matching apply module locally on the user's Mac. Invoked every 5 min
by macOS launchd via scripts/apply-worker-local.sh.

Reads from cloud Supabase, dispatches to the existing per-source apply
modules. The user still clicks Submit on the Mac — the worker only fills.
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

from sidegig.db import (
    _client,
    claim_one_pending_apply_request,
    get_latest_draft_for_listing,
    mark_apply_request_done,
    mark_apply_request_failed,
    recover_stale_apply_claims,
)

log = logging.getLogger("apply-worker")


def _fetch_listing(listing_id: str) -> dict[str, Any] | None:
    res = _client().table("listings").select("*").eq("id", listing_id).limit(1).execute()
    return res.data[0] if res.data else None


def _fetch_latest_draft(listing_id: str) -> dict[str, Any] | None:
    return get_latest_draft_for_listing(listing_id)


def _render_cv_pdf(cv_markdown: str) -> Path:
    """Render the adapted CV markdown to a temp PDF and return its path."""
    from sidegig.cv_render import cv_markdown_to_pdf

    out = Path(tempfile.mkstemp(suffix=".pdf")[1])
    cv_markdown_to_pdf(cv_markdown, out)
    return out


def process_one(row: dict[str, Any]) -> None:
    """Dispatch a single apply_request to the right per-source apply module.

    All errors are caught and marked as `failed` on the row so the loop
    survives. Stale-claim recovery handles the case where this function
    itself crashes before marking the row done/failed.
    """
    request_id = row["id"]
    try:
        listing = _fetch_listing(row["listing_id"])
        if listing is None:
            raise RuntimeError(f"listing {row['listing_id']} not found")
        draft = _fetch_latest_draft(row["listing_id"])
        if draft is None:
            raise RuntimeError(f"no draft for listing {row['listing_id']}")
        cv_pdf_path = _render_cv_pdf(draft["adapted_cv"])

        source = row["source"]
        if source == "upwork":
            from sidegig.apply import upwork as upwork_mod

            upwork_mod.apply(
                listing["url"],
                draft["body"],
                cv_pdf_path,
                listing_title=listing.get("title") or "",
                listing_description=listing.get("description") or "",
                adapted_cv_md=draft["adapted_cv"],
            )
        elif source == "freelancermap":
            from sidegig.apply import freelancermap as fm_mod

            fm_mod.apply(listing["url"], draft["body"], cv_pdf_path)
        elif source in ("bundesagentur", "linkedin"):
            from sidegig.apply import external_ats

            ats_url = (listing.get("raw") or {}).get("externeUrl") or listing["url"]
            external_ats.apply(
                ats_url=ats_url,
                proposal=draft["body"],
                cv_pdf_path=cv_pdf_path,
                listing_title=listing.get("title") or "",
                listing_description=listing.get("description") or "",
                adapted_cv_md=draft["adapted_cv"],
            )
        else:
            raise RuntimeError(f"unknown source: {source!r}")

        mark_apply_request_done(request_id, executed_draft_id=draft["id"], notes=None)
    except Exception as e:
        log.exception("apply request %s failed", request_id)
        mark_apply_request_failed(request_id, error=str(e), notes=None)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    recovered = recover_stale_apply_claims()
    if recovered:
        log.info("recovered %d stale claim(s)", recovered)
    processed = 0
    while True:
        row = claim_one_pending_apply_request()
        if row is None:
            break
        log.info("processing apply_request %s (source=%s)", row["id"], row["source"])
        process_one(row)
        processed += 1
    log.info("worker done — processed %d request(s)", processed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
poetry run pytest tests/test_apply_worker.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Run ruff to confirm lint clean**

```bash
poetry run ruff check sidegig/apply/worker.py tests/test_apply_worker.py
```

Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add sidegig/apply/worker.py tests/test_apply_worker.py
git commit -m "feat(apply): worker module — claim, dispatch, mark done/failed"
```

---

### Task 7: Launchd wrapper script + plist

**Files:**
- Create: `scripts/apply-worker-local.sh`
- Create: `scripts/com.sidegig.apply-worker.plist`

- [ ] **Step 1: Write the bash wrapper**

Create `scripts/apply-worker-local.sh`:

```bash
#!/usr/bin/env bash
# Local apply-worker, designed for macOS launchd.
#
# Polls cloud Supabase for pending apply_requests; runs the matching
# per-source apply module against the user's CDP-attached Chrome.
# Notifies on failure so silent crashes are visible.
#
# Install:
#   cp scripts/com.sidegig.apply-worker.plist ~/Library/LaunchAgents/
#   launchctl load ~/Library/LaunchAgents/com.sidegig.apply-worker.plist
#
# Manual smoke test:
#   bash scripts/apply-worker-local.sh

set -uo pipefail

REPO_DIR="${SIDEGIG_REPO:-$HOME/projects/sidegig}"
LOG_DIR="$HOME/.cache/sidegig/launchd"
LOG_FILE="$LOG_DIR/apply-worker.log"
CDP_PORT="${CDP_PORT:-9222}"

mkdir -p "$LOG_DIR"

notify() {
  local title="$1" body="$2"
  osascript -e "display notification \"$body\" with title \"$title\" sound name \"Funk\"" 2>/dev/null \
    || echo "[notify-fallback] $title — $body" >> "$LOG_FILE"
}

ts() { date '+%Y-%m-%dT%H:%M:%S%z'; }

echo "" >> "$LOG_FILE"
echo "==== $(ts) apply-worker starting ====" >> "$LOG_FILE"

# Cheap CDP probe — open a TCP connection to the debug port.
# Skip silently if Chrome isn't up AND there are no pending rows. If
# pending rows exist, surface a notification so the user knows.
if ! lsof -nP -iTCP:"$CDP_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  pending=$(
    cd "$REPO_DIR" && \
    "${POETRY_BIN:-poetry}" run dotenv run -- python -c "
from sidegig.db import list_apply_requests
n = sum(1 for r in list_apply_requests(limit=50) if r['status'] == 'pending')
print(n)
" 2>/dev/null || echo 0
  )
  if [[ "${pending:-0}" -gt 0 ]]; then
    notify "sidegig: $pending apply request(s) waiting" \
      "Start Chrome with: bash scripts/chrome-cdp.sh"
  fi
  echo "$(ts) CDP Chrome down; pending=$pending — exiting" >> "$LOG_FILE"
  exit 0
fi

cd "$REPO_DIR" || { notify "sidegig apply-worker" "cd $REPO_DIR failed"; exit 1; }

POETRY="${POETRY_BIN:-/opt/homebrew/bin/poetry}"
if [[ ! -x "$POETRY" ]]; then POETRY="$(command -v poetry || true)"; fi
if [[ -z "$POETRY" ]]; then
  notify "sidegig apply-worker" "poetry not found — set POETRY_BIN env"
  exit 127
fi

UPWORK_CDP_URL="http://localhost:$CDP_PORT" \
  "$POETRY" run dotenv run -- python -m sidegig.apply.worker >> "$LOG_FILE" 2>&1
status=$?

if [[ $status -ne 0 ]]; then
  tail_lines="$(tail -5 "$LOG_FILE" | tr '\n' ' ' | cut -c1-240)"
  notify "sidegig apply-worker FAILED (exit $status)" "$tail_lines"
  echo "$(ts) FAILED exit=$status" >> "$LOG_FILE"
  exit "$status"
fi

echo "$(ts) OK" >> "$LOG_FILE"
```

- [ ] **Step 2: Make it executable + lint**

```bash
chmod +x scripts/apply-worker-local.sh
shellcheck scripts/apply-worker-local.sh
```

Expected: no output (clean).

- [ ] **Step 3: Write the launchd plist**

Create `scripts/com.sidegig.apply-worker.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyLists-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.sidegig.apply-worker</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/izabelcvetkovic/projects/sidegig/scripts/apply-worker-local.sh</string>
  </array>

  <!-- Poll every 5 minutes. Counts from agent load time; after Mac
       reboot the schedule may shift by a few minutes. Acceptable. -->
  <key>StartInterval</key>
  <integer>300</integer>

  <key>EnvironmentVariables</key>
  <dict>
    <key>SIDEGIG_REPO</key>
    <string>/Users/izabelcvetkovic/projects/sidegig</string>
    <key>POETRY_BIN</key>
    <string>/opt/homebrew/bin/poetry</string>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>

  <key>StandardOutPath</key>
  <string>/Users/izabelcvetkovic/.cache/sidegig/launchd/apply-worker.launchd.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/izabelcvetkovic/.cache/sidegig/launchd/apply-worker.launchd.log</string>

  <!-- Don't run multiple instances; the worker is single-tenant against CDP. -->
  <key>AbandonProcessGroup</key>
  <false/>
</dict>
</plist>
```

- [ ] **Step 4: Smoke-test the wrapper (no install yet)**

```bash
bash scripts/apply-worker-local.sh
tail -10 ~/.cache/sidegig/launchd/apply-worker.log
```

Expected: log ends with `OK` (or "CDP Chrome down; pending=0 — exiting" if Chrome isn't up).

- [ ] **Step 5: Commit**

```bash
git add scripts/apply-worker-local.sh scripts/com.sidegig.apply-worker.plist
git commit -m "feat(scripts): launchd apply-worker wrapper + plist (every 5 min)"
```

---

### Task 8: Streamlit dual-mode — env detection + Google auth gate

**Files:**
- Modify: `sidegig/ui/app.py`

- [ ] **Step 1: Add deploy-mode detection + auth gate at top of app.py**

In `sidegig/ui/app.py`, just after the existing `import streamlit as st` and `from sidegig.models import ListingStatus`, insert:

```python
import os

_SIDEGIG_DEPLOYED = bool(os.environ.get("SIDEGIG_DEPLOYED"))


def _auth_gate() -> None:
    """When deployed, gate the app behind st.login() (Google OIDC).
    No-op when running locally (`make ui`)."""
    if not _SIDEGIG_DEPLOYED:
        return
    if not st.user.is_logged_in:
        st.title("sidegig")
        st.markdown("Sign in to view your pipeline.")
        if st.button("Sign in with Google", type="primary"):
            st.login()
        st.stop()
```

Then call `_auth_gate()` right after `st.set_page_config(...)`:

```python
st.set_page_config(page_title="sidegig", layout="wide", initial_sidebar_state="expanded")
_auth_gate()
```

- [ ] **Step 2: Run lint**

```bash
poetry run ruff check sidegig/ui/app.py
```

Expected: `All checks passed!`

- [ ] **Step 3: Smoke-test local mode (no auth)**

```bash
make ui
# In another terminal:
curl -s -I http://localhost:8501 | head -1
```

Expected: `HTTP/1.1 200 OK` and the app loads without auth. Press Ctrl-C when done.

- [ ] **Step 4: Smoke-test deployed mode locally**

```bash
SIDEGIG_DEPLOYED=1 make ui
```

Expected: page shows "Sign in with Google" button. (Clicking it will fail without OAuth configured — that's correct, just verify the gate appears.) Ctrl-C.

- [ ] **Step 5: Commit**

```bash
git add sidegig/ui/app.py
git commit -m "feat(ui): SIDEGIG_DEPLOYED env + st.login() gate when deployed"
```

---

### Task 9: Streamlit dual-mode — queue button + hide local-only buttons

**Files:**
- Modify: `sidegig/ui/app.py`

- [ ] **Step 1: Replace per-source auto-apply buttons with a single queue button when deployed**

Find the three per-source `🤖 Auto-fill on …` button blocks in `sidegig/ui/app.py` (around lines for `row.get("source") == "freelancermap"`, `row.get("source") == "upwork"`, and `row.get("source") in ("linkedin", "bundesagentur")`). Wrap each existing block in `if not _SIDEGIG_DEPLOYED:` so they only run locally. Then add a unified queue button that runs only when deployed.

Insert this new block (right before the `st.caption("Or do steps individually:")` line that follows the existing auto-fill buttons):

```python
# Deployed mode: replace all three subprocess-spawning auto-fill buttons
# with a single "Queue auto-apply on Mac" button. Inserts an
# apply_requests row; the local launchd worker picks it up within 5 min.
if _SIDEGIG_DEPLOYED and row.get("source") in (
    "upwork", "freelancermap", "bundesagentur", "linkedin"
):
    from sidegig.db import insert_apply_request, list_apply_requests

    pending_for_this_listing = [
        r for r in list_apply_requests(limit=50)
        if r["listing_id"] == row["id"] and r["status"] in ("pending", "processing")
    ]
    already_queued = len(pending_for_this_listing) > 0

    if st.button(
        ("⏳ Already queued — your Mac will pick it up within 5 min"
         if already_queued else "🤖 Queue auto-apply on Mac"),
        key=f"queue-apply-{row['id']}",
        disabled=already_queued,
        type=("secondary" if already_queued else "primary"),
        help=(
            "Inserts a request into the apply queue. The launchd worker "
            "on your Mac runs every 5 minutes — it picks up the request, "
            "fills the form, and pauses at Submit for you to click."
        ),
    ):
        try:
            insert_apply_request(listing_id=row["id"], source=row["source"])
            st.toast("Queued — your Mac will pick this up within 5 minutes.")
            st.rerun()
        except Exception as e:
            st.error(f"Queue insert failed: {e}")
```

- [ ] **Step 2: Hide local-only buttons when deployed**

Find the "Export CV PDF" and "Open & ready" button blocks; wrap each in `if not _SIDEGIG_DEPLOYED:` so they only render locally. (Both rely on local filesystem / `webbrowser.open()` which don't work on Streamlit Cloud.)

- [ ] **Step 3: Lint**

```bash
poetry run ruff check sidegig/ui/app.py
```

Expected: `All checks passed!`

- [ ] **Step 4: Smoke-test queue-insert locally**

```bash
SIDEGIG_DEPLOYED=1 make ui
```

Open `http://localhost:8501`, log in (will fail without OAuth — that's fine, skip with `st.experimental_set_query_params` workaround OR test by removing the auth gate temporarily). Click "Queue auto-apply on Mac" on a drafted listing. Verify a row appears in cloud Supabase:

```bash
PYTHONPATH=. poetry run dotenv run -- python -c "
from sidegig.db import list_apply_requests
for r in list_apply_requests(limit=5):
    print(r['status'], r['source'], r['listing_id'])
"
```

Expected: at least one row with `pending` status.

- [ ] **Step 5: Run end-to-end with worker**

In one terminal, leave SIDEGIG_DEPLOYED=1 Streamlit running. In another, run the worker against the queued row:

```bash
PYTHONPATH=. poetry run dotenv run -- python -m sidegig.apply.worker
```

Expected log: `processing apply_request <id> (source=...)` followed by `worker done — processed 1 request(s)`. Status of the row should transition to `done` or `failed` in the DB.

- [ ] **Step 6: Commit**

```bash
git add sidegig/ui/app.py
git commit -m "feat(ui): queue-mode auto-apply button + hide local-only buttons when deployed"
```

---

### Task 10: Streamlit — "Apply queue" panel

**Files:**
- Modify: `sidegig/ui/app.py`

- [ ] **Step 1: Add a queue-status section to the Pipeline tab sidebar**

In `sidegig/ui/app.py`, inside the `with tab_pipeline:` block, after the existing sidebar filters (after `sort_by = st.selectbox(...)`), add:

```python
        # Apply queue panel — only meaningful when deployed (or when the
        # local worker has run).
        st.markdown("### Apply queue")
        from sidegig.db import list_apply_requests as _list_apply_requests

        queue_rows = _list_apply_requests(limit=10)
        if not queue_rows:
            st.caption("Queue empty.")
        else:
            for q in queue_rows:
                status_color = {
                    "pending": "🕐",
                    "processing": "⚙️",
                    "done": "✅",
                    "failed": "❌",
                }.get(q["status"], "•")
                short_id = q["listing_id"][:8]
                line = f"{status_color} `{short_id}` {q['source']} — {q['status']}"
                st.caption(line)
                if q.get("error"):
                    st.caption(f"   ↳ {q['error'][:120]}")
```

- [ ] **Step 2: Lint**

```bash
poetry run ruff check sidegig/ui/app.py
```

Expected: `All checks passed!`

- [ ] **Step 3: Smoke-test the panel**

```bash
make ui  # local mode is fine; the panel reads cloud DB regardless
```

Open http://localhost:8501. Expected: sidebar shows the queue rows (any from prior smoke tests) with status icons.

- [ ] **Step 4: Commit**

```bash
git add sidegig/ui/app.py
git commit -m "feat(ui): apply-queue status panel in sidebar"
```

---

### Task 11: Setup runbook — `docs/phase11a-setup.md`

**Files:**
- Create: `docs/phase11a-setup.md`

- [ ] **Step 1: Write the runbook**

Create `docs/phase11a-setup.md`:

```markdown
# Phase 11a setup — deploy dashboard + install local worker

Steps you run manually after the code is in place.

## 1. Apply the apply_requests migration to cloud Supabase

Already done in Task 1 of the implementation plan. Verify:

\`\`\`bash
PYTHONPATH=. poetry run dotenv run -- python -c "
from sidegig.db import _client
print(_client().table('apply_requests').select('id', head=True, count='exact').execute().count)
"
\`\`\`

Expected: a number (≥0), no error.

## 2. Create the Google OAuth client

1. Go to https://console.cloud.google.com/apis/credentials.
2. Create a project (e.g., \`sidegig\`) if you don't have one.
3. Configure OAuth consent screen → External → fill in name, support email, your Gmail.
4. Credentials → Create Credentials → OAuth client ID → Web application.
5. Authorized redirect URI: \`https://<your-streamlit-app>.streamlit.app/oauth2callback\`
   (Use a placeholder for now; you'll update it after deploy.)
6. Copy the **Client ID** and **Client secret** somewhere safe.

## 3. Connect Streamlit Cloud to your GitHub repo

1. Go to https://share.streamlit.io and sign in with GitHub.
2. New app → Pick \`Izabel94/sidegig\`, branch \`main\`, file \`sidegig/ui/app.py\`.
3. Advanced settings → Python version 3.13.
4. **Don't deploy yet** — secrets first.

## 4. Paste secrets into Streamlit Cloud

In the same "Advanced settings" dialog, under "Secrets", paste:

\`\`\`toml
SIDEGIG_DEPLOYED = "1"
SUPABASE_URL = "https://mrqsvbiarormusmgxzrm.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "<your service_role JWT>"
LLM_PROVIDER = "gemini"
GEMINI_API_KEY = "<your Gemini key>"
SCRAPER_CONTACT_EMAIL = "izabelcvetkovic@gmail.com"

[auth]
redirect_uri = "https://<your-streamlit-app>.streamlit.app/oauth2callback"
cookie_secret = "<random 64-char hex — generate with `openssl rand -hex 32`>"
client_id = "<google client id from step 2>"
client_secret = "<google client secret from step 2>"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
\`\`\`

Click Save, then Deploy.

## 5. Update Google OAuth redirect URI with the real Streamlit URL

After deploy, Streamlit Cloud assigns you a URL like
\`https://sidegig-izabel94.streamlit.app\`. Go back to the Google Cloud
Console (step 2.5) and replace the placeholder redirect URI with the
real \`<that-url>/oauth2callback\`. Save.

Update the same value in Streamlit Cloud secrets (\`redirect_uri\` under \`[auth]\`). The app will redeploy.

## 6. Install the local launchd worker

\`\`\`bash
cp scripts/com.sidegig.apply-worker.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.sidegig.apply-worker.plist
\`\`\`

Verify it's loaded:

\`\`\`bash
launchctl list | grep com.sidegig
\`\`\`

Expected: two lines (one for the upwork-discover job from Phase 10, one for this apply-worker).

## 7. Smoke test end-to-end

1. On your phone, open the deployed Streamlit URL.
2. Sign in with Google.
3. Pick any drafted listing. Click **🤖 Queue auto-apply on Mac**.
4. On your Mac, start CDP Chrome: \`bash scripts/chrome-cdp.sh\` (if not already running).
5. Wait up to 5 minutes for launchd to fire (you can force it with
   \`launchctl start com.sidegig.apply-worker\`).
6. Watch your CDP Chrome — a new tab opens with the apply form. Don't
   click Submit; verify the form is filled correctly.
7. Check the dashboard's "Apply queue" sidebar — the row should show
   ✅ done.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Sign in with Google" loops back | redirect_uri mismatch | Re-check that Google Console URI matches Streamlit secrets exactly |
| Queue insert succeeds but worker never picks up | launchd not loaded, or CDP Chrome down | \`launchctl list \| grep com.sidegig.apply-worker\` + start \`chrome-cdp.sh\` |
| Worker fires but Chrome doesn't open | Wrong source dispatch | Check \`~/.cache/sidegig/launchd/apply-worker.log\` |
| Row stuck in \`processing\` for >30 min | Worker crashed | Next worker run auto-resets to \`pending\` |
\`\`\`

- [ ] **Step 2: Commit**

\`\`\`bash
git add docs/phase11a-setup.md
git commit -m "docs(phase-11a): setup runbook for Google OAuth + Streamlit Cloud + launchd worker"
\`\`\`

---

### Task 12: Final lint + test sweep + push

- [ ] **Step 1: Full lint + tests**

\`\`\`bash
poetry run ruff check sidegig/ scripts/ tests/
poetry run pytest -q
\`\`\`

Expected: ruff clean; all tests pass (102+ existing + new from Tasks 2-6).

- [ ] **Step 2: Push to GitHub**

\`\`\`bash
git push origin feat/ai-sidejob-auto-applier:main
\`\`\`

Expected: fast-forward push, no conflicts.

- [ ] **Step 3: Confirm GHA cron still works after the changes**

\`\`\`bash
gh workflow run daily.yml --repo Izabel94/sidegig --ref main
gh run watch --repo Izabel94/sidegig
\`\`\`

Expected: green run. The new queue table doesn't interfere with the existing cron.

---

## Done criteria

After Tasks 1-12, the user can:
- Open the deployed Streamlit URL on her phone, sign in with Google
- See her pipeline + the apply queue panel
- Click "Queue auto-apply on Mac" on any drafted listing
- Walk to her Mac (CDP Chrome up), wait up to 5 min
- See the apply form filled in Chrome, review it, click Submit
- The queue row transitions from `pending` → `processing` → `done` (or `failed`) visible in dashboard

## Out of scope for this plan (reaffirming spec)

- Multi-user / multi-tenancy
- Windows/Linux equivalents
- Auto-retry of failed requests
- Always-on daemon
- Realtime webhooks
- WeasyPrint on Streamlit Cloud

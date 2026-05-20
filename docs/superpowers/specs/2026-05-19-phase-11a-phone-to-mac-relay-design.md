# Phase 11a — Phone-to-Mac Apply Relay (Design)

**Status:** Approved 2026-05-19. Implementation plan to be drafted next.
**Scope:** Single-user (Izabel only). Multi-user / cross-platform are explicit non-goals.

## Problem

The Streamlit dashboard's auto-apply buttons spawn subprocesses that
attach to `localhost:9222` — the user's CDP Chrome. This couples the
dashboard to the Mac and prevents phone-based triage. Cloud-deploying the
dashboard naively would break every apply button: the cloud host's
`localhost` has no Chrome.

The user wants to triage listings from their phone (commute, lunch break)
while keeping the apply execution on their Mac, where their authenticated
Chrome sessions live and Cloudflare/Cloudflare-Turnstile mitigations work.

## Constraints (user decisions captured during brainstorming)

| Decision | Choice |
|---|---|
| End goal | Single-user (Izabel). Multi-user lives in a separate fork. |
| What's queued | Fill only — user clicks Submit on the Mac (same safety rail as today). |
| Dashboard host | Streamlit Community Cloud, free tier. Private GitHub repo. |
| Auth | Google OIDC via `st.login()` (native Streamlit 1.32+). |
| Queue data shape | Reference + late-bind. Worker fetches latest draft at execute-time. |
| Always-on processes | Forbidden. launchd scheduled poll, not persistent daemon. |
| Cross-platform | Out of scope. Mac launchd only. |

## Architecture

```
┌────────────────────────────────────┐
│ Streamlit Cloud (deployed)         │
│ • Google sign-in (st.login)       │
│ • Read cloud Supabase             │
│ • Triage: accept/reject listings  │
│ • Preview/re-draft proposal+CV    │
│ • "Queue auto-apply" → inserts    │
│   apply_requests row, status=     │
│   pending                          │
└────────────┬───────────────────────┘
             │
             ▼ insert (listing_id only — late-bind to latest draft)
┌────────────────────────────────────┐
│ Cloud Supabase                     │
│ • NEW: apply_requests table        │
│ • Existing: listings, drafts, etc. │
└────────────┬───────────────────────┘
             │
             ▼ poll every 5min via launchd
┌────────────────────────────────────┐
│ Local worker (your Mac)            │
│ • Atomic claim ONE pending row     │
│ • Fetch listing + latest draft     │
│ • Render CV PDF locally            │
│ • Dispatch by source → apply       │
│   module (upwork / FM / external)  │
│ • Mark done / failed               │
│ • Notify on failure                │
└────────────────────────────────────┘
```

## Components

### 1. Schema — `apply_requests` table (cloud Supabase)

```sql
create table apply_requests (
  id                 uuid primary key default gen_random_uuid(),
  listing_id         uuid not null references listings(id) on delete cascade,
  source             text not null,                -- copied from listings.source at insert
  status             text not null default 'pending',  -- pending|processing|done|failed
  error              text,
  requested_at       timestamptz not null default now(),
  claimed_at         timestamptz,                   -- when worker started; stale-claim if >30min
  completed_at       timestamptz,
  executed_draft_id  uuid references drafts(id),   -- audit: which draft the worker actually used
  notes              text                            -- worker log tail
);
create index on apply_requests (status, requested_at);
```

Migration lives at `supabase/migrations/<timestamp>_apply_requests.sql`.

### 2. Streamlit dual-mode (`sidegig/ui/app.py`)

Single env flag `SIDEGIG_DEPLOYED` switches behavior:

```python
DEPLOYED = bool(os.environ.get("SIDEGIG_DEPLOYED"))

if DEPLOYED:
    # Auth gate first
    if not st.user.is_logged_in:
        if st.button("Sign in with Google"):
            st.login()
        st.stop()
    # Auto-apply buttons → write to apply_requests instead of subprocess
    # Hide "Export CV PDF" (WeasyPrint not on Streamlit Cloud)
else:
    # Local: current behavior, unchanged
```

Specific UI changes when `DEPLOYED=1`:

- Replace the 3 auto-apply button branches (upwork / freelancermap /
  external_ats) with a single "Queue auto-apply on Mac" button that
  inserts into `apply_requests`.
- Disable "Open & ready" (relies on local `webbrowser.open()`).
- Disable "Export CV PDF" (no WeasyPrint).
- Keep "Draft / Re-draft proposal & adapt CV" — runs on cloud via the
  LLM call, doesn't need Chrome.
- Keep "Copy proposal" — `pyperclip` fails silently on cloud; we show
  the text in a text area so the user can long-press-copy on phone.
- Show a new "Apply queue" panel listing recent `apply_requests` with
  status + error notes. Lets the user re-queue failed ones.

### 3. Worker module (`sidegig/apply/worker.py`)

```python
def claim_one_pending() -> Row | None:
    # Atomic claim — supabase doesn't support RETURNING via REST client,
    # so we do this in two steps with optimistic concurrency:
    # 1. select the oldest pending row
    # 2. update WHERE id=X AND status='pending' SET status='processing', claimed_at=now()
    # If rowcount==0, another worker grabbed it — retry select.
    ...

def process_one(row):
    listing = get_listing(row["listing_id"])
    draft = get_latest_draft_for_listing(row["listing_id"])
    cv_pdf_path = render_cv_pdf(draft["adapted_cv"])
    if row["source"] == "upwork":
        sidegig.apply.upwork.apply(...)
    elif row["source"] == "freelancermap":
        sidegig.apply.freelancermap.apply(...)
    elif row["source"] in ("bundesagentur", "linkedin"):
        sidegig.apply.external_ats.apply(...)
    mark_done(row["id"], executed_draft_id=draft["id"])

def recover_stale_claims():
    # status='processing' AND claimed_at > 30min ago → reset to pending
    ...

def main():
    recover_stale_claims()
    while True:
        row = claim_one_pending()
        if row is None:
            return
        try:
            process_one(row)
        except Exception as e:
            mark_failed(row["id"], error=str(e), notes=tail_of_log())
```

Module is invoked as `python -m sidegig.apply.worker` from launchd.

### 4. Worker scheduler — `scripts/apply-worker-local.sh` + `.plist`

- launchd every 5 minutes (`StartCalendarInterval` array with 12 entries
  per hour, OR `StartInterval=300`)
- Pre-check: if CDP Chrome not on :9222 AND there are pending rows →
  macOS notification: "X apply requests waiting, start Chrome with
  `bash scripts/chrome-cdp.sh`"
- On worker exit != 0 → macOS notification with the tail of the error
- Same shape as the existing `scripts/upwork-discover-local.sh`. Plist
  template copied from `scripts/com.sidegig.upwork-discover.plist`.

### 5. Streamlit Cloud deployment

One-time setup checklist (lives in `docs/phase11a-setup.md`, written
during implementation):

1. Apply the `apply_requests` migration to cloud Supabase.
2. Google Cloud Console: create OAuth 2.0 client. Authorized redirect
   URI = the Streamlit Cloud app URL + `/oauth2callback`.
3. Streamlit Cloud: connect to `Izabel94/sidegig` (private repo).
4. Paste secrets via Advanced Settings:
   ```toml
   SIDEGIG_DEPLOYED = "1"
   SUPABASE_URL = "https://mrqsvbiarormusmgxzrm.supabase.co"
   SUPABASE_SERVICE_ROLE_KEY = "..."
   LLM_PROVIDER = "gemini"
   GEMINI_API_KEY = "..."
   SCRAPER_CONTACT_EMAIL = "izabelcvetkovic@gmail.com"

   [auth]
   redirect_uri = "https://<your-app>.streamlit.app/oauth2callback"
   cookie_secret = "<random 64-char hex>"
   client_id = "<google oauth client id>"
   client_secret = "<google oauth client secret>"
   server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
   ```
5. Install local launchd worker:
   ```bash
   cp scripts/com.sidegig.apply-worker.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.sidegig.apply-worker.plist
   ```
6. Smoke test: open deployed URL, sign in, queue an apply on a low-stakes
   listing. Wait ≤5 min. Confirm Mac launchd fires and Chrome opens.

## Failure handling

| Scenario | Behavior | User-visible |
|---|---|---|
| Mac asleep | launchd defers; row stays `pending`. | "Apply queue" panel shows status. |
| CDP Chrome not running | Worker exits with notification; row stays `pending`. | macOS banner: "X requests waiting, start Chrome". |
| Listing expired | apply CTA not found → `failed` with notes. | Status `failed` in queue panel; re-queue or skip. |
| LLM error | `failed` with error message. | Same — re-queue. |
| Worker crash mid-apply | Stale-claim recovery resets row on next worker run. | Row goes back to `pending`, retries on next cycle. |
| Two workers race | Atomic claim ensures one winner per row. | Invisible — system handles. |
| Supabase project pause (7d no activity) | Daily cron keeps it alive. If broken cron for >7d, project pauses; deployed dashboard returns 500. | Cron failures already email user (GHA default). |

## Testing

1. **Schema test** — table creation, FK cascade, unique constraints.
2. **Worker unit tests** — `claim_one_pending`, `recover_stale_claims`,
   `process_one` dispatch (with mocked apply modules).
3. **Worker integration test (local)** — insert a `pending` row pointing
   at a test listing; run `python -m sidegig.apply.worker`; verify row
   transitions to `done` with `executed_draft_id` populated.
4. **Streamlit dual-mode test** — run `make ui` with `SIDEGIG_DEPLOYED=1`
   locally; confirm queue insert happens instead of subprocess.
5. **End-to-end smoke** — deployed dashboard → queue → wait for launchd
   → verify Chrome opens.

## Out of scope (YAGNI)

- Multi-user / multi-tenancy (Phase 12 if shipping to others)
- Windows/Linux launchd equivalents (Phase 12)
- Auto-retry of failed requests (user re-queues manually)
- Always-on Python daemon (launchd scheduled = enough)
- Realtime Postgres webhooks (5-min poll = enough)
- WeasyPrint on Streamlit Cloud (PDF render stays local in worker)
- Multiple concurrent local workers (single launchd entry; atomic claim
  protects in case of overlap)

## Open questions / known unknowns

- **Streamlit Cloud cold-start delay** — apps that sleep can take ~30s
  to wake on a phone tap. Acceptable for a triage app but worth knowing.
  Mitigation: daily cron run hits the cloud Supabase, which doesn't keep
  the Streamlit app warm. Could add a daily curl to the Streamlit URL
  if cold starts become annoying.
- **Google OAuth redirect_uri** must match the deployed URL exactly.
  Update both Google Cloud Console and `secrets.toml` after first deploy.
- **launchd `StartInterval` vs `StartCalendarInterval`** — `StartInterval`
  fires every N seconds but counts from agent load time. After Mac
  reboot, the schedule may shift. `StartCalendarInterval` with 12 fixed
  minutes per hour is more predictable but verbose. Plan to start with
  `StartInterval=300` and switch if drift becomes an issue.

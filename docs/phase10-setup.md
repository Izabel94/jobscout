# Phase 10 setup — cloud Supabase + daily cron

Steps you run manually to wire this up. Code-side artifacts (workflow,
launchd plist, digest script) are already in the repo.

## 1. Create the cloud Supabase project

1. Sign up / log in at https://supabase.com.
2. Create a new project (free tier). Pick the EU region (`fra` Frankfurt
   or `eu-west`) for latency from Germany.
3. Save the database password somewhere; you won't need it for the cron
   but it's the only time Supabase shows it.
4. After the project provisions, go to **Project Settings → API** and copy:
   - **Project URL** → this becomes `SUPABASE_URL`
   - **service_role** key → this becomes `SUPABASE_SERVICE_ROLE_KEY`
   - The `anon` key isn't used in cron; it's only for the Streamlit
     dashboard if you ever expose it publicly.

## 2. Apply the schema to cloud Supabase

The local stack has `supabase/migrations/20260513000000_initial_schema.sql`.
Apply it to cloud:

```bash
# Install the supabase CLI if you don't have it
brew install supabase/tap/supabase

# Link the local project to your cloud project
supabase link --project-ref <your-project-ref>

# Push migrations
supabase db push
```

Alternatively: open the Supabase dashboard → SQL Editor, paste the
contents of `supabase/migrations/20260513000000_initial_schema.sql`, run.

## 3. (Optional) Migrate existing local data to cloud

If you want to keep what's currently in your local DB (listings, drafts,
scores), dump and restore:

```bash
# From your local supabase (running on :54322 by default)
pg_dump -h localhost -p 54322 -U postgres -d postgres \
  --data-only --schema=public > /tmp/sidegig-local.sql

# Restore to cloud — get the connection string from
# Supabase dashboard → Project Settings → Database
psql "<cloud connection string>" < /tmp/sidegig-local.sql
```

Skip this if you'd rather start with an empty cloud DB and let the next
cron run populate it.

## 4. Switch your local `.env` to cloud (when you want)

Currently your `.env` points at `http://localhost:54321`. To run the
local Streamlit against cloud, replace those two values:

```dotenv
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<the service_role key from step 1>
```

Keep local Supabase as a dev sandbox if you like — toggle the .env values
to switch between local and cloud.

## 5. Add GitHub Actions secrets

Go to https://github.com/<your-user>/sidegig/settings/secrets/actions and
add these repository secrets:

| Secret name | Value |
|-------------|-------|
| `SUPABASE_URL` | Your cloud project URL from step 1 |
| `SUPABASE_SERVICE_ROLE_KEY` | Your cloud service_role key |
| `LLM_PROVIDER` | `gemini` (or `anthropic`) |
| `GEMINI_API_KEY` | Your Gemini key |
| `ANTHROPIC_API_KEY` | (optional, only if LLM_PROVIDER=anthropic) |
| `SCRAPER_CONTACT_EMAIL` | `izabelcvetkovic@gmail.com` |
| `FREELANCERMAP_PROFILE_B64` | (optional — see below) |

**Optional: persistent freelancermap session.** If you want logged-in FM
scraping in cron, tar+base64 your local profile and paste it as the
secret value:

```bash
tar -czC ~/.cache/sidegig -f - freelancermap-profile | base64 > /tmp/fm-profile.b64
# Then copy /tmp/fm-profile.b64 into the secret in the GitHub UI
```

If the secret isn't set, the workflow falls back to logged-out FM
scraping (still works, just fewer results).

## 6. Trigger the workflow

After secrets are in place:

```bash
# Manual run via gh CLI (one-off, no need to wait for the schedule)
gh workflow run daily.yml
gh run watch
```

Or push any change to trigger the next scheduled run at 09:50 UTC
(10:50 / 11:50 Berlin local depending on DST).

## 7. Install the local Upwork cron (macOS launchd)

Upwork can't run in GHA (Cloudflare blocks Playwright). Local cron handles
it whenever your Mac is awake AND `bash scripts/chrome-cdp.sh` is running:

```bash
cp scripts/com.sidegig.upwork-discover.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.sidegig.upwork-discover.plist
```

It runs Mon–Fri at 11:00 local. On failure (CDP Chrome not running,
network error, etc.) it pops a macOS notification with the reason — you
won't miss broken runs. Logs land in `~/.cache/sidegig/launchd/`.

Smoke-test it once:

```bash
bash scripts/upwork-discover-local.sh
# Expected: silent success, ~30s. If CDP Chrome isn't up, you'll see a
# notification banner from System Notifications.
```

## 8. Verify everything works

After a successful cron run, you can read the digest from the GHA log:

1. GitHub → Actions → Daily → click the latest run
2. Open the `score` job
3. Expand the **"Print digest to GHA log"** step

You'll see a table of new high-scoring listings + per-source ingestion
counts. No email, no extra service — just the GHA log.

## Failure visibility

- **GHA cron failures**: GitHub emails you by default when a workflow you
  watch fails. Confirm at Settings → Notifications.
- **Local launchd failures**: macOS notification with the error tail.
  Logs at `~/.cache/sidegig/launchd/upwork-discover.log`.
- **Both jobs run independently**: a broken GHA run doesn't stop the
  local launchd job, and vice versa.

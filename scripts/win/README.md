# Jobscout on Windows — operator install runbook

This is the **manual** Windows install path. The Briefcase MSI installer is a
Phase 5b follow-up; for now the operator runs these steps once on the end-user
laptop.

## Prerequisites

- Windows 10/11.
- Google Chrome installed (or Microsoft Edge, which is preinstalled).
- Python 3.13 (install from python.org or the Microsoft Store).
- Git for Windows.

## Install

1. Clone the repo to the user's home directory:

   ```cmd
   cd %USERPROFILE%
   git clone <repo-url> jobscout
   cd jobscout
   ```

2. Install Poetry and the project deps:

   ```cmd
   pip install poetry
   poetry install
   ```

3. Create `%USERPROFILE%\jobscout\.env` with the required keys:

   ```
   SUPABASE_URL=https://<project-ref>.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=<key>
   GEMINI_API_KEY=<key>
   JOBSCOUT_PROFILE_LINKEDIN_URL=https://www.linkedin.com/in/<the-end-user>/
   ```

4. Sign into LinkedIn in the CDP Chrome window once so the profile persists:

   ```cmd
   scripts\win\chrome-cdp.bat
   ```

   A Chrome window opens on LinkedIn. Sign in, close the window when done.

5. Register the two Task Scheduler tasks (paths are absolute so they work
   regardless of where the user installs):

   ```cmd
   schtasks /Create /TN "Jobscout\ApplyWorker" /XML "%USERPROFILE%\jobscout\scripts\win\JobscoutApplyWorker.xml" /F
   schtasks /Create /TN "Jobscout\Discover" /XML "%USERPROFILE%\jobscout\scripts\win\JobscoutDiscover.xml" /F
   ```

   `/F` overwrites any pre-existing task with the same name (idempotent re-install).

6. Verify the tasks registered:

   ```cmd
   schtasks /Query /TN "Jobscout\ApplyWorker"
   schtasks /Query /TN "Jobscout\Discover"
   ```

   Both should show `Ready` status.

7. Trigger an immediate apply-worker run to confirm clean exit:

   ```cmd
   schtasks /Run /TN "Jobscout\ApplyWorker"
   ```

   Wait ~10 seconds, then check the log:

   ```cmd
   type "%LOCALAPPDATA%\jobscout\logs\apply-worker.log"
   ```

   Expected last lines:
   - `CDP Chrome down; pending=0 — exiting` (if Chrome is closed), OR
   - `worker done — processed 0 request(s)` + `OK` (if Chrome is up + no pending rows).

## Daily workflow

- Once per day, launch the CDP Chrome window: `scripts\win\chrome-cdp.bat`.
- Open the Streamlit dashboard, click Apply on listings.
- The Task Scheduler `Jobscout\ApplyWorker` task fires every 5 min, claims pending rows, fills the form, pauses on Submit.
- Review what got filled in the Chrome window, click Submit yourself.
- Close the Chrome window when done.

## Uninstall

```cmd
schtasks /Delete /TN "Jobscout\ApplyWorker" /F
schtasks /Delete /TN "Jobscout\Discover" /F
rmdir /S /Q "%LOCALAPPDATA%\jobscout"
```

Then `rmdir /S /Q "%USERPROFILE%\jobscout"` if you want to remove the repo too.

## Troubleshooting

- **Toast notifications don't appear:** the toast API isn't available when
  the task runs under a non-interactive context. Check
  `%LOCALAPPDATA%\jobscout\logs\notify.log` — failures are appended there as
  a fallback.
- **`apply-worker.bat` exits with code 127:** the venv isn't built. Re-run
  `poetry install` from `%USERPROFILE%\jobscout`.
- **`apply-worker.bat` exits with the Supabase 404 error:** the
  `apply_requests` table isn't in your Supabase project. Apply the migration
  `supabase/migrations/20260522140000_apply_requests.sql` via the dashboard
  SQL editor.
- **Edge is launched instead of Chrome:** `JOBSCOUT_CHROME_BIN` env var
  wasn't set and Chrome isn't at the standard install path. Either install
  Chrome or set `JOBSCOUT_CHROME_BIN` in the user's environment variables
  (Control Panel → System → Advanced → Environment Variables).

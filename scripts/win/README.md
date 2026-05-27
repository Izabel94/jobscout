# Jobscout on Windows — operator runbook

Phase 5b ships a one-time ZIP bootstrap. The operator builds it on her Windows
laptop, drops it in Syncthing, and the end user double-clicks `install.bat`.
After that, code updates flow automatically via the hourly `Jobscout\Update`
task — no re-ship, no re-install.

Architecture: discovery + apply both run **locally on the end-user laptop**, the
same 5-min-poll model sidegig uses on the operator's Mac (here: 1-min poll). The
Streamlit dashboard runs on Streamlit Cloud and is reached from any browser.

## One-time operator setup (before first build)

1. **Generate a read-only deploy key** for the repo:

   ```cmd
   ssh-keygen -t ed25519 -f jobscout_deploy -N "" -C "jobscout-deploy"
   ```

   Add `jobscout_deploy.pub` to the repo's **Settings → Deploy keys** (read-only,
   do NOT check "Allow write access"). Keep `jobscout_deploy` (private) safe — it
   goes on the end-user machine later. Deploy keys are single-repo scoped and
   don't expire, unlike fine-grained PATs.

## Build the package (on the operator's Windows laptop)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\win\build-package.ps1
```

Produces `dist\jobscout-windows-<date>.zip` containing: the repo (with `.git`,
origin preset to the SSH URL), a python.org user-scope installer, MinGit, and the
bootstrap scripts. Drop the ZIP in the Syncthing folder shared with the end user.

> Build must run on Windows — Python wheels (lxml, sentence-transformers,
> playwright) are platform-specific; there is no cross-build from macOS.

## End-user install (they do this)

See [`INSTALL.md`](INSTALL.md) — extract ZIP, double-click `install.bat`, wait,
text the operator. `install.bat` lays down the repo, a Python venv + deps,
Playwright's chromium, Chrome (Edge fallback), and the four Task Scheduler tasks,
and starts the CDP Chrome.

## Operator finish (once, via RDP)

After the user reports "Install complete":

1. Drop the **private** deploy key at `%USERPROFILE%\.ssh\jobscout_deploy`.
2. Paste the real secrets into `%USERPROFILE%\jobscout\.env`:

   ```
   SUPABASE_URL=https://<project-ref>.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=<key>
   GEMINI_API_KEY=<key>
   JOBSCOUT_PROFILE_LINKEDIN_URL=https://www.linkedin.com/in/<the-end-user>/
   JOBSCOUT_CDP_URL=http://localhost:9222
   ```

3. Smoke the four tasks and the deploy-key fetch:

   ```cmd
   schtasks /Query /TN "Jobscout\Chrome"
   schtasks /Query /TN "Jobscout\Update"
   schtasks /Query /TN "Jobscout\ApplyWorker"
   schtasks /Query /TN "Jobscout\Discover"
   schtasks /Run /TN "Jobscout\Update"
   type "%LOCALAPPDATA%\jobscout\logs\update.log"
   ```

   The update log should end with `OK` (proves the deploy key authenticates).

## The four tasks

| Task | Trigger | Does |
|---|---|---|
| `Jobscout\Chrome` | at logon | launches the CDP Chrome, stays open all day |
| `Jobscout\Update` | hourly + at logon | `git fetch` + `git reset --hard origin/main`, re-pip on dep change |
| `Jobscout\ApplyWorker` | every 1 min | claims one pending apply_request, fills the form |
| `Jobscout\Discover` | daily 10:30 Berlin | LinkedIn + Indeed scrape → Supabase |

## Daily workflow (end user)

- CDP Chrome is already open (logon task). Open the dashboard from the desktop
  shortcut, click Apply on listings.
- Within ~1 min the form fills in a Chrome tab. Review, click Submit, close the tab.

## Updates

Push to `main`. Within the hour, `Jobscout\Update` resets the end-user's repo to
`origin/main` and re-pips if `requirements.win.txt` changed. **Keep `main` green** —
a broken commit auto-deploys. `git reset --hard` (not `pull --ff-only`) so a
crash/AV-dirtied tree can't silently strand the user on stale code.

## Uninstall

Run `scripts\win\uninstall.bat` (deletes the four tasks + shortcut, prompts to
remove program files), or manually:

```cmd
schtasks /Delete /TN "Jobscout\Chrome" /F
schtasks /Delete /TN "Jobscout\Update" /F
schtasks /Delete /TN "Jobscout\ApplyWorker" /F
schtasks /Delete /TN "Jobscout\Discover" /F
rmdir /S /Q "%LOCALAPPDATA%\jobscout"
rmdir /S /Q "%USERPROFILE%\jobscout"
```

## Troubleshooting

- **`update.log` shows "deploy key missing":** drop the private key at
  `%USERPROFILE%\.ssh\jobscout_deploy` via RDP.
- **`update.log` fetch FAILED:** the public key isn't on the repo's Deploy Keys,
  or the private key on disk doesn't match. Re-add it.
- **Toasts don't appear:** check `%LOCALAPPDATA%\jobscout\logs\notify.log` (fallback log).
- **`apply-worker.bat` exits 127:** venv missing — re-run `install.bat`.
- **`apply-worker.bat` Supabase 404:** the `apply_requests` table isn't in the
  Supabase project; apply the migration via the dashboard SQL editor.
- **Edge launched instead of Chrome:** expected if Chrome install fell back to
  Edge — check `%LOCALAPPDATA%\jobscout\browser.txt`.

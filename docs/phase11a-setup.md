# Phase 11a setup — deploy dashboard + install local worker

Steps you run manually after the code is in place.

## 1. Apply the apply_requests migration to cloud Supabase

Already done as part of Task 1 of the implementation. Verify:

```bash
PYTHONPATH=. poetry run dotenv run -- python -c "
from sidegig.db import _client
print(_client().table('apply_requests').select('id', head=True, count='exact').execute().count)
"
```

Expected: a number (≥0), no error.

## 2. Create the Google OAuth client

1. Go to https://console.cloud.google.com/apis/credentials.
2. Create a project (e.g., `sidegig`) if you don't have one.
3. Configure OAuth consent screen → External → fill in name, support email, your Gmail.
4. Credentials → Create Credentials → OAuth client ID → Web application.
5. Authorized redirect URI: `https://<your-streamlit-app>.streamlit.app/oauth2callback`
   (Use a placeholder for now; you'll update it after deploy.)
6. Copy the **Client ID** and **Client secret** somewhere safe.

## 3. Connect Streamlit Cloud to your GitHub repo

1. Go to https://share.streamlit.io and sign in with GitHub.
2. New app → Pick `Izabel94/sidegig`, branch `main`, file `sidegig/ui/app.py`.
3. Advanced settings → Python version 3.13.
4. **Don't deploy yet** — secrets first.

## 4. Paste secrets into Streamlit Cloud

In the same "Advanced settings" dialog, under "Secrets", paste:

```toml
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
```

Click Save, then Deploy.

## 5. Update Google OAuth redirect URI with the real Streamlit URL

After deploy, Streamlit Cloud assigns you a URL like
`https://sidegig-izabel94.streamlit.app`. Go back to the Google Cloud
Console (step 2.5) and replace the placeholder redirect URI with the
real `<that-url>/oauth2callback`. Save.

Update the same value in Streamlit Cloud secrets (`redirect_uri` under `[auth]`). The app will redeploy.

## 6. Install the local launchd worker

```bash
cp scripts/com.sidegig.apply-worker.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.sidegig.apply-worker.plist
```

Verify it's loaded:

```bash
launchctl list | grep com.sidegig
```

Expected: two lines (one for the upwork-discover job from Phase 10, one for this apply-worker).

## 7. Smoke test end-to-end

1. On your phone, open the deployed Streamlit URL.
2. Sign in with Google.
3. Pick any drafted listing. Click **🤖 Queue auto-apply on Mac**.
4. On your Mac, start CDP Chrome: `bash scripts/chrome-cdp.sh` (if not already running).
5. Wait up to 5 minutes for launchd to fire (you can force it with
   `launchctl start com.sidegig.apply-worker`).
6. Watch your CDP Chrome — a new tab opens with the apply form. Don't
   click Submit; verify the form is filled correctly.
7. Check the dashboard's "Apply queue" sidebar — the row should show
   ✅ done.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Sign in with Google" loops back | redirect_uri mismatch | Re-check that Google Console URI matches Streamlit secrets exactly |
| Queue insert succeeds but worker never picks up | launchd not loaded, or CDP Chrome down | `launchctl list \| grep com.sidegig.apply-worker` + start `chrome-cdp.sh` |
| Worker fires but Chrome doesn't open | Wrong source dispatch | Check `~/.cache/sidegig/launchd/apply-worker.log` |
| Row stuck in `processing` for >30 min | Worker crashed | Next worker run auto-resets to `pending` |

# jobscout

Hamburg-region full-time job discovery + AI drafting for a non-technical end user.
Forked from `sidegig` with these material differences:

- Sources: LinkedIn + Indeed only (no Upwork / Bundesagentur / freelancermap)
- Roles: full-time / permanent only
- Geography: Hamburg only
- Apply: external-ATS only, never LinkedIn Easy Apply (Phase 4, separate plan)
- UI consumer: a non-technical end user on Windows (Phase 3, separate plan)
- Profile: stored in DB, not YAML

See `docs/superpowers/specs/2026-05-20-jobscout-design.md` for the design.

## Setup (operator, one-time per new end-user)

1. `cp .env.example .env` and fill in:
   - `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (new jobscout project)
   - `GEMINI_API_KEY` (carry over from sidegig)
   - `JOBSCOUT_PROFILE_LINKEDIN_URL` — end user's LinkedIn URL (set after running bootstrap)
2. `make install`
3. Apply Supabase migrations:
   ```
   /opt/homebrew/opt/libpq/bin/psql "postgresql://postgres:$SUPABASE_DB_PASSWORD@db.<project-ref>.supabase.co:5432/postgres" -f supabase/migrations/20260520120000_initial_schema.sql
   /opt/homebrew/opt/libpq/bin/psql "postgresql://postgres:$SUPABASE_DB_PASSWORD@db.<project-ref>.supabase.co:5432/postgres" -f supabase/migrations/20260520120100_profiles.sql
   ```
4. Bootstrap the end user's profile (one-time per new user):
   ```
   make bootstrap-profile LINKEDIN_URL=https://www.linkedin.com/in/<the-user>/
   ```
5. Set `JOBSCOUT_PROFILE_LINKEDIN_URL` in `.env` to the URL from step 4.

## Daily run (Phase 0–2 scope — manual)

```
make discover    # scrape LinkedIn + Indeed, persist to Supabase
make filter      # apply hard filters (drop part-time/contract/intern, drop high-confidence onsite)
make score       # LLM-score survivors with Gemini Flash
```

Phases 3–6 (separate plans) add Streamlit UI, apply pipeline, Windows installer, handover.

## Phase 0 — classifier maintenance

If JobSpy fields shift or the classifier's accuracy on real listings drops:

```
poetry run python scripts/capture_fixtures.py    # refresh corpus
poetry run python scripts/label_fixtures.py      # regenerate regex-heuristic labels
poetry run pytest tests/test_derive_*.py -v      # verify classifiers
```

The classifier code in `jobscout/derive.py` and the labeller in `scripts/label_fixtures.py` share regex patterns by design — fixture tests catch drift between them.

## Development

```
make test    # full pytest suite (99 tests, all passing)
make lint    # ruff check + format-check
make type    # mypy strict
```

## Streamlit Cloud deploy (Phase 3 UI)

1. Push the repo to GitHub (private, gitignored .env stays out).
2. In Streamlit Cloud → New app → point at `jobscout/ui/app.py` on the main branch.
3. Set these app secrets in Streamlit Cloud's dashboard:
   - `JOBSCOUT_DEPLOYED=1`
   - `JOBSCOUT_PASSWORD=<end-user-password>`
   - `JOBSCOUT_PROFILE_LINKEDIN_URL=<the end user's linkedin url>`
   - `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `GEMINI_API_KEY` — same values as `.env`.
4. Streamlit Cloud reads `requirements.txt` (not pyproject.toml) — keep both in sync when adding deps.
5. After deploy, the app shows the password gate. Sign in with `JOBSCOUT_PASSWORD`. Tabs are Pipeline + Settings.

## UI development

```
make ui     # launch Streamlit locally at http://localhost:8501
```

The Pipeline tab shows KPI hero + filter chips + paginated listing cards (cards have a green left-border accent for viewed listings — auto-marked on expand, per sidegig commit 559c15c). The Settings tab edits the profile row directly via DB upsert.

## Project status

- Phase 0–2 (this codebase): data backbone — sources, derived classifiers, schema, profile bootstrap, scoring + drafting pipeline. Complete.
- Phase 3: Streamlit UI with shadcn-ui card layout + Settings tab + hidden /admin route. Separate plan.
- Phase 4: Apply pipeline — external_ats.py + worker.py port, page.pdf() CV render, macOS launchd plist for dev. Separate plan.
- Phase 5: Windows installer (Briefcase MSI), Task Scheduler, post/pre-install scripts. Separate plan.
- Phase 6: Operator handover. Separate plan.

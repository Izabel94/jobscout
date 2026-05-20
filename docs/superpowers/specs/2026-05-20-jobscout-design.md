# jobscout — design

**Status:** brainstorming complete, awaiting review
**Date:** 2026-05-20
**Source project:** [sidegig](../../../) — fork-and-strip, not greenfield

> Note: this file is a local working artifact per the user's
> `no-commit-specs-or-plans` convention. Do not commit.

---

## 1. What this is

A single-user fork of sidegig for a non-technical end user on Windows. Same
pipeline shape (discover → filter → score → draft → human-in-the-loop apply),
restricted to full-time / permanent roles in Germany via LinkedIn and Indeed,
with all apply automation routed exclusively through external ATS forms
(never LinkedIn Easy Apply) to keep ban risk low.

**Operator** (you, Izabel): runs one-time bootstrap scripts on a Mac to seed
the user's profile from their LinkedIn URL and (later) CV. Does not run
anything daily. Develops and tests entirely on macOS using sidegig's existing
launchd plists.

**End user**: a non-technical person on a Windows PC. The dashboard is
browser-agnostic — Streamlit runs in any modern browser (Chrome / Edge /
Firefox / Brave), user picks. The CDP-attached **apply popup** requires a
Chromium-family browser because Playwright's `connect_over_cdp()` only
supports Chrome DevTools Protocol (Firefox dropped CDP for WebDriver BiDi
in 2023 — `connect_over_cdp` doesn't work there). The installer prefers
Chrome (well-tested by sidegig); if Chrome isn't present and the user
doesn't want to install it, the installer falls back to Microsoft Edge,
which is preinstalled on every Windows 10/11 and is fully Chromium-based —
the same CDP code path works unchanged. Configurable via `JOBSCOUT_CHROME_BIN`
env var (sidegig already takes `CHROME_BIN`; same pattern).

Daily interaction: open dashboard in whatever browser they prefer, click
Apply on listings they like, click Submit in the popup Chrome/Edge.

## 2. Architecture

```
   ┌─────────────────────────────────────────────────────┐
   │  user's Windows PC                                   │
   │                                                       │
   │  ┌──────────────────┐    ┌──────────────────┐       │
   │  │ Task Scheduler    │    │  Chrome (CDP)    │       │
   │  │  • discover 10:30 │    │  port 9222        │       │
   │  │  • apply  @5min   │    │  user-logged-in   │       │
   │  └──────────────────┘    └─────────▲────────┘       │
   │           │                          │                │
   │           │  writes/reads            │ CDP attach     │
   │           ▼                          │                │
   │    [Supabase Cloud]                  │                │
   │    listings/drafts/                  │                │
   │    apply_requests/                   │                │
   │    submissions/profiles              │                │
   │           ▲                          │                │
   │           │                          │                │
   │           │             [Python: apply.worker         │
   │           │              + external_ats.py]           │
   │           │                                            │
   └───────────┼───────────────────────────────────────────┘
               │
               ▼
   [Streamlit Cloud — opens in any browser]
       Pipeline tab • Settings tab • hidden /admin
```

Cost: €0 infra (Supabase free, Streamlit free) + LLM tokens (Gemini Flash
Lite, ~€2–5/month at expected volume).

## 3. Sources, derived fields, and the filter-validation contract

**Sources (drop everything else from sidegig):**
- LinkedIn via JobSpy (`linkedin_fetch_description=True`, `is_remote=True`, `hours_old=72`).
- Indeed via JobSpy (`country_indeed="germany"`, same params).

**New derived fields on `listings`:**

| field | LinkedIn signal | Indeed signal | UNKNOWN policy |
|---|---|---|---|
| `arrangement` (REMOTE / HYBRID / ONSITE / UNKNOWN) | Title/desc/location keyword classifier (DE+EN: *remote*, *hybrid*, *home office*, *vor Ort*, *im Büro*, *on-site*, *Präsenz*, *days/week in office*). LLM tiebreaker when keyword classifier is ambiguous. | Prefer JobSpy's `work_from_home_type` field when present, else same keyword classifier as LinkedIn. | Don't filter; pass to LLM scorer with the literal evidence string. |
| `job_type` (FULLTIME / PERMANENT / CONTRACT / PARTTIME / INTERN / UNKNOWN) | JobSpy `job_type` field (sometimes empty) + DE/EN regex over text (*Festanstellung*, *unbefristet*, *Vollzeit*, *full-time*, *permanent*, *contract*, *Werkstudent*, *Praktikum*). | Same as LinkedIn. | Don't filter; pass to LLM. |
| `apply_method` (EASY_APPLY / EXTERNAL_APPLY) | **Presence of `JobPost.company_url_direct`** (parsed by JobSpy from LinkedIn's `applyUrl` code block on the listing detail page; requires `linkedin_fetch_description=True`, which sidegig already passes). Present → EXTERNAL_APPLY, use `company_url_direct` as `ats_url`. Absent → EASY_APPLY (apply happens in-page on linkedin.com, surfaced for manual). Note: JobSpy's `easy_apply` parameter is a request-side filter (README says it "no longer works"), not a response field — don't read from it. | Same pattern via Indeed's apply-URL parsing. Present → EXTERNAL_APPLY. Absent → EASY_APPLY (Indeed-internal). | Apply worker also re-checks at click time as a belt-and-suspenders: if it lands on `linkedin.com/jobs/easyApply/*` despite EXTERNAL_APPLY classification, abort and re-mark the row. |
| `arrangement_evidence`, `job_type_evidence` | The literal substring matched by the classifier, for auditing. | Same. | Empty string. |

**Filter rules:**
1. DROP if `job_type ∈ {CONTRACT, PARTTIME, INTERN}` — full-time/permanent only.
2. DROP if `arrangement == ONSITE` AND classifier confidence is high (literal "5 days/week in office", "fully on-site", "vollständig vor Ort", etc.). Hybrid + UNKNOWN both pass through.
3. KEEP rate filter shape but treat absent rate as pass (full-time DE listings often omit salary).
4. KEEP skill-keyword + title-denylist + embedding filters, seeded from `profiles` row (NOT `config/profile.yaml`).

**Filter-validation contract — non-negotiable per
[feedback_test_filters_against_real_data](../../../../../.claude/projects/-Users-izabelcvetkovic-projects-sidegig/memory/feedback_test_filters_against_real_data.md):**

- **Phase 0:** `scripts/capture_fixtures.py` dumps ≥30 raw LinkedIn + ≥30 raw Indeed payloads, all Hamburg-region (operator scoped to Hamburg only — no Berlin / München mix). Cover remote/hybrid/onsite × fulltime/contract within Hamburg. Persists as JSON under `tests/fixtures/listings/`.
- **Classifier test suite drives the classifier code.** For each fixture, hand-label `expected_arrangement`, `expected_job_type`, `expected_apply_method` in sibling `.labels.json`. Classifiers ship only when they hit ≥95% accuracy on the labelled corpus.
- **Inline vocabulary docs** in `derive.py` listing actual distinct values seen per source per field with counts. No guessing.
- **Weekly drift check** re-captures 10 fresh listings and asserts field vocabulary hasn't shifted. Fails loud.
- **End-to-end smoke** runs the full pipeline against fixtures with mocked LLM and asserts known pass/drop set + kept-rate baseline ±10%.

## 4. Schema (Supabase migrations)

Identical to sidegig with these deltas:

```sql
-- listings: restrict source enum, add derived columns
alter table listings
  add column arrangement text,
  add column arrangement_evidence text,
  add column job_type text,
  add column job_type_evidence text,
  add column apply_method text;

-- profiles: single-row, editable in Streamlit Settings tab
create table profiles (
  id              uuid primary key default gen_random_uuid(),
  full_name       text not null,
  email           text,
  phone           text,
  linkedin_url    text not null unique,
  location        text,
  languages       jsonb not null default '{}'::jsonb,
  years_experience integer,
  headline        text,
  summary         text,
  skills          text[] not null default array[]::text[],
  positions       jsonb not null default '[]'::jsonb,
  education       jsonb not null default '[]'::jsonb,
  target_rate_floor_eur numeric,
  required_skill_keywords text[] not null default array[]::text[],
  title_denylist  text[] not null default array[]::text[],
  anchor_summaries jsonb not null default '[]'::jsonb,
  arrangement_preferences text[] not null default array['remote','hybrid']::text[],
  cv_markdown     text,
  cv_uploaded_at  timestamptz,
  linkedin_scraped_at timestamptz,
  updated_at      timestamptz not null default now()
);

-- onboarding_targets: dropped entirely (sidegig had it; we don't need it)

-- apply_requests: kept unchanged from sidegig (bridges cloud UI ↔ local worker)
-- drafts, submissions, source_runs: unchanged from sidegig
```

## 5. Apply architecture — sidegig model, ported to Windows

**External ATS only — never LinkedIn Easy Apply.** This is the highest-leverage
risk reduction we make.

```
user clicks Apply in dashboard
   │
   ▼
Streamlit inserts apply_requests row (status=pending)
   │
   ▼   (Windows Task Scheduler fires apply-worker.bat every 5 min)
worker.bat probes Chrome CDP port (9222)
   ├─ Chrome down + pending rows → Windows toast: "Start Chrome shortcut", exit 0
   └─ Chrome up → invoke python -m jobscout.apply.worker (timeout 240s)
                  │
                  ▼
worker claims one row → loads listing + latest draft → renders CV PDF
   │
   ▼
external_ats.apply(...) attaches via connect_over_cdp("http://localhost:9222")
   │
   ▼
walks Apply CTAs (3 hops) → kills cookie banners → enumerates fields
   → LLM produces actions JSON → applies with paced fills
   → page.wait_for_event("close") — user clicks Submit, closes tab
   │
   ▼
worker marks row status=done, records submission
```

**Files ported from sidegig (largely unchanged):**
- `sidegig/apply/worker.py` → `jobscout/apply/worker.py`. Drop upwork/freelancermap branches; route all sources through `external_ats`.
- `sidegig/apply/external_ats.py` → `jobscout/apply/external_ats.py`. Carry the LLM-driven fill, CTA walking, cookie-banner dismissal, field enumeration, paced fill, `wait_for("close")` submit signal.
- `sidegig/browser_session.py` → `jobscout/browser_session.py` unchanged.
- `sidegig/cv_render.py` → `jobscout/cv_render.py` **rewritten** to use Chrome instead of WeasyPrint. WeasyPrint on Windows requires manual MSYS2 + Pango install (`WEASYPRINT_DLL_DIRECTORIES` env var), which can't ship in a one-click installer. New render path: take CV markdown → render to HTML via Jinja2 (already a dep) → load HTML in CDP Chrome via `page.set_content(html)` → call `page.pdf(format="A4", print_background=True)` → save bytes. Zero new native deps; reuses the Chrome instance we already have. Tradeoff: requires Chrome to be up at draft time, which it is during apply but isn't necessarily during discovery. Move CV-PDF rendering to apply-worker (just before form fill), not draft-time — matches sidegig's worker.py:_render_cv_pdf flow.
- Drop entirely: `sidegig/apply/upwork.py`, `sidegig/apply/freelancermap.py`, `sidegig/sources/{upwork,bundesagentur,freelancermap}.py`.

**Files new for Windows:**
- `scripts/win/chrome-cdp.bat` — equivalent of `chrome-cdp.sh`. Launches `C:\Program Files\Google\Chrome\Application\chrome.exe --remote-debugging-port=9222 --user-data-dir=%LOCALAPPDATA%\jobscout\chrome-cdp`.
- `scripts/win/apply-worker.bat` — equivalent of `apply-worker-local.sh`. Probes CDP via PowerShell `Test-NetConnection localhost -Port 9222`. On Chrome-down + pending rows, sends Windows toast via `notifypy` Python lib (cross-platform — same code path used on macOS for dev).
- `scripts/win/discover.bat` — invokes `python -m jobscout.discover`.
- `scripts/win/JobscoutApplyWorker.xml`, `JobscoutDiscover.xml` — Task Scheduler definitions. Both run as the logged-in user. Apply: `StartInterval=300`. Discover: daily 10:30 Berlin time (Europe/Berlin, DST-aware via Task Scheduler's local-time semantics) with `RunIfMissed=true`.
- `scripts/win/installer/` — Briefcase MSI project (Briefcase 0.3.25+, WiX 5.0.2). **Post-install script** (`scripts/win/post_install.ps1`) registers the two Task Scheduler entries via `schtasks /create /XML ...`, drops the desktop shortcut "Start jobscout Chrome" pointing at `chrome-cdp.bat`, and installs Chrome silently if absent (falls back to using preinstalled Edge if Chrome install fails). **Pre-uninstall script** (`scripts/win/pre_uninstall.ps1`) deletes both Task Scheduler entries via `schtasks /delete /TN ... /F` — mandatory for MSI clean-state obligations.

**Cross-platform development on Mac:**
- All Python code is identical on both OSes.
- Sidegig's existing `scripts/chrome-cdp.sh` and `com.sidegig.apply-worker.plist` adapt one-to-one — keep them in the repo as `scripts/mac/*` for dev.
- Notifications use `notifypy` (Python lib, abstracts macOS osascript / Windows toast / Linux libnotify) — one code path, works everywhere.
- Operator's daily loop: develop on Mac → `make smoke` → `bash scripts/mac/chrome-cdp.sh` for manual end-to-end test → install macOS launchd plist for soak.
- Pre-handoff verification: operator has a physical Windows laptop on hand. Run the installer on it once per Phase 5/6 milestone, verify Task Scheduler + Chrome CDP + apply flow end-to-end, then ship. No rented cloud VM, no virtualisation.

**Apply daily cap:** hard 10/day total across all sources (was 5/source/day in sidegig — too high given 2026 LinkedIn enforcement landscape). Counted from `submissions` rolling 24h. Dashboard surfaces "X/10 applies remaining today."

**Easy Apply listings:** populated by discovery, retained in DB with `apply_method=EASY_APPLY`. Surfaced in dashboard under a separate section with "Open in LinkedIn — proposal copied to clipboard." User does the 60-second click flow themselves. No auto-apply path touches Easy Apply.

## 6. Discovery — cron on the user's PC

GH Actions runs on Azure IPs which LinkedIn blocks at ASN level (instant 403)
([Proxies.sx 2026 guide](https://www.proxies.sx/blog/linkedin-proxy-automation-guide-2026)).
Discovery moves to the user's PC, same approach sidegig used for Upwork
(launchd) but now for LinkedIn + Indeed too.

- Windows Task Scheduler triggers `discover.bat` daily at 10:30 Berlin time.
- `RunIfMissed=true` catches the case where the PC was off at 10:30; the run fires on next boot.
- Discovery is logged-out JobSpy (no LinkedIn cookies needed for discovery; lower account exposure). Sidegig's `sources/linkedin.py` carries over almost verbatim, with `sleep_jitter(3.0)` keeping us under LinkedIn's ~20-req/hr threshold.
- New `sources/indeed.py` follows the same pattern.
- Output writes to Supabase Cloud — Streamlit dashboard reads from there.

## 7. Honest risk profile

This is what I overstated initially and what the research corrected.

**Discovery risk: LOW.** Logged-out JobSpy on a residential IP at <20 req/hr is well-trodden. No cookie exposure. Worst case: LinkedIn temporarily rate-limits the IP, JobSpy returns fewer results that day.

**Auto-apply risk (external ATS only): LOW–MEDIUM.** The apply happens on the company's ATS site, not on linkedin.com. LinkedIn's bot-detection stack doesn't see the form fill at all. CDP detection at the ATS form layer (Greenhouse, Lever, Workable) is much less aggressive than on linkedin.com. Sidegig's paced-fill + real-Chrome-via-CDP pattern is appropriate here.

**Easy Apply risk: would be HIGH if we automated it.** We don't.
- "LinkedIn banned 40% of accounts on non-compliant tools in Q1 2026" ([Syntora](https://syntora.io/solutions/linkedin-automation-without-the-ban-risk---whats-actually-working-in-2026)).
- Safe Easy Apply velocity per their detection ML: <15/day; we cap at 10/day total apply.
- Even with residential IP, CDP detection at `linkedin.com/jobs/easyApply/*` is plausible ([Castle.io](https://blog.castle.io/how-to-detect-headless-chrome-bots-instrumented-with-playwright/), [Rebrowser](https://rebrowser.net/blog/how-to-fix-runtime-enable-cdp-detection-of-puppeteer-playwright-and-other-automation-libraries)).
- We surface Easy Apply listings for manual one-click apply — user remains in full control on the highest-risk surface.

**What still requires care:**
- Daily-cap monitoring; never exceed 10 applies/day cap regardless of pipeline output.
- The classifier that distinguishes EASY_APPLY vs EXTERNAL_APPLY must be defensive: when uncertain, default to EASY_APPLY (manual route). False positives (treating an external as Easy Apply) cost convenience, not the account. False negatives (auto-applying Easy Apply) cost the account.
- Sidegig's paced-fill timing (`_FIELD_THINK_SECONDS=(0.6, 1.8)`) is fine for external ATS; on LinkedIn it would be insufficient per the 2026 ML update — but we never use it there.

## 8. UI scope

Streamlit dashboard with three views (sidegig's `app.py` adapted):
- **Pipeline tab** — ranked listings with score, score rationale, derived fields visible, draft preview, Apply button (auto-fires `external_ats` flow), or "Open in LinkedIn" button for Easy Apply.
- **Settings tab** — `profiles` row editor (rate floor, skill keywords, title denylist, arrangement preferences). Read-write to DB.
- **Hidden `/admin` route** — operator-only (you), shows source_runs, ingestion counts, recent errors. Password-gated separately.

Drop the Onboarding tab entirely. Drop the Observability tab from the
user-facing UI (folded into `/admin`).

**Visual quality bar — meaningfully nicer than sidegig's dashboard.**
Sidegig's UI is operator-grade (dense tables, plain Streamlit defaults).
This one is going to a non-technical end user who will judge the product by
how it looks. Concretely:

- **Card-based listing layout** instead of dense tables. Each listing is a
  `st.container(border=True)` with: company logo (favicon fallback via
  `https://www.google.com/s2/favicons?domain=…`), title + company in a
  typographic hierarchy, score as a coloured pill (`>80` green, `60–80`
  amber, `<60` grey), derived-field pills for arrangement / job_type /
  apply_method, posted-date, location, then expandable proposal preview and
  primary CTA.
- **Use `streamlit-shadcn-ui`** (`pip install streamlit-shadcn-ui`) for
  buttons, badges, cards, and tabs that look polished out of the box —
  shadcn primitives ported to Streamlit. Falls back to native Streamlit if a
  component is missing.
- **Custom theme** in `.streamlit/config.toml`: light/dark aware, neutral
  palette, generous spacing. Avoid the default red `primaryColor`.
- **Hero row at top of Pipeline** — "X new today · Y applied today · Z/10
  remaining" as 3 KPI tiles, using `streamlit-shadcn-ui` cards or just
  `st.metric` in three columns with a custom CSS lift.
- **Empty / loading / error states** are designed, not default — friendly
  text and a skeleton during fetch, a clear "no new listings today, check
  back tomorrow at 10:30" empty state, a "something broke — operator has
  been notified" error state.
- **Easy Apply vs External Apply visually distinct**: External Apply rows
  show a primary "Apply" button (filled, brand colour). Easy Apply rows show
  a secondary "Open in LinkedIn" button + small "proposal copied to
  clipboard" affordance, with a tooltip explaining why these are manual.
- **Listing list virtualised / paginated** at 20 per page — sidegig's
  unbounded list slowed Streamlit reruns once the DB grew.
- **No emojis** in UI strings (organisation policy + visual cleanliness).
  Use icons from the shadcn icon set (`lucide` icons under the hood) where a
  glyph helps.

Out of scope visually for MVP: dark/light toggle (system-preference only),
animations, mobile layout (desktop-only — user is on a Windows PC), custom
fonts beyond what `streamlit-shadcn-ui` ships.

## 9. Profile bootstrap (one-time, operator-run on Mac)

- `scripts/bootstrap_profile_from_linkedin.py` — operator runs locally, points Playwright at the operator's logged-in LinkedIn session, navigates to the user's profile URL, scrapes structured data via DOM selectors + LLM extract, upserts to Supabase `profiles` row. No paid API.
- `scripts/bootstrap_profile_from_cv.py` — operator runs locally when CV arrives, reads CV PDF, LLM extracts → merges into same `profiles` row.
- Both upsert by `linkedin_url` unique key.

## 10. What's in / out of scope

**In scope (the MVP build):**
- Fork sidegig → new repo (placeholder name `jobscout`).
- Drop: upwork, bundesagentur, freelancermap sources + apply modules; Onboarding tab; Observability tab.
- Adapt: `linkedin.py` source; add `indeed.py`.
- New: `derive.py` for arrangement/job_type/apply_method classifiers with fixture-driven tests.
- New: `profiles` table + bootstrap scripts.
- New: Settings tab and hidden `/admin` route in Streamlit.
- Port: apply pipeline to Windows (.bat, Task Scheduler XML, Briefcase installer).
- Invert: filters from "drop full-time" to "drop part-time/contract/intern".
- Risk cap: 10/day total auto-apply, EXTERNAL_APPLY only.

**Out of scope (deferred):**
- Multi-tenant / signup / Supabase Auth.
- Cloud headless apply (Browserbase) — not needed once external-ATS-only is locked in.
- Firefox extension.
- Email digest (sidegig has the code; port later if user complains they miss listings).
- Upwork / Bundesagentur / freelancermap.
- macOS/Linux end-user support — Windows-only installer for now (operator dev path on Mac is separate).
- Per-tenant LLM budgets, billing.
- Score feedback loop (thumbs up/down).

**Decided in the spec (operator can override before plan):**
- Project name: `jobscout` (placeholder).
- LLM provider: Gemini, models `gemini-3.1-flash-lite` for score and draft (sidegig defaults).
- Email digest: deferred to post-MVP.

## 10b. Open assumptions to verify in Phase 0

These are claims I've made in the spec without external verification (web
search was rate-limited at spec-writing time). Phase 0 verifies each before
the rest of the milestones execute. If a verification fails, the spec gets a
targeted patch and a delta-review with the operator before continuing.

| # | assumption | how to verify in Phase 0 | fallback if it fails |
|---|---|---|---|
| A1 | ~~JobSpy's response for LinkedIn / Indeed does not include a clean `apply_method` field.~~ **RESOLVED with correction.** Initial code grep was sloppy — line 313's `easy_apply` is in `ScraperInput` (request-side filter that JobSpy README says "no longer works"), **not** in `JobPost`. The actual per-job signal is `JobPost.company_url_direct` (line 249), populated when JobSpy parses LinkedIn's `applyUrl` code block from the detail page (requires `linkedin_fetch_description=True`, sidegig already does this). Present → EXTERNAL_APPLY; absent → EASY_APPLY. Spec updated. Apply-time belt-and-suspenders check still applies. | — | — |
| A2 | `streamlit-shadcn-ui` is real, installable via pip, and supports the components named in Section 8 (button, badge, card, tabs, metric). | **VERIFIED via context7 docs.** Package exists at `/observedobserver/streamlit-shadcn-ui-docs`; `ui.card`, `ui.button`, `ui.input`, `ui.element` for nested layouts all confirmed in their official docs. **Caveat: Context7 flags source reputation as "Low"** — it's a community package, not first-party shadcn. Good enough for MVP visual quality bar. | If maintenance becomes a concern post-MVP, fall back to plain Streamlit + custom CSS via `st.html`. |
| A3 | ~~WeasyPrint installs cleanly on Windows for CV PDF rendering.~~ **FAILED VERIFICATION via official WeasyPrint docs.** Windows install requires manual MSYS2 + Pango + `WEASYPRINT_DLL_DIRECTORIES=C:\msys64\mingw64\bin` env var. Non-starter for a non-tech user installer. **Spec updated:** `cv_render.py` rewritten to use `page.pdf()` on the CDP Chrome we already have running — zero new native deps. CV PDF render moves from draft-time to apply-time (just before form fill), matching sidegig's worker.py:_render_cv_pdf flow. | — | — |
| A4 | Playwright's `connect_over_cdp` works against Microsoft Edge on Windows (Edge is Chromium-based, ships with CDP). | On the Windows laptop, launch Edge with `--remote-debugging-port=9222`, run sidegig's `external_ats.apply()` against a test listing. | If Edge surprisingly doesn't work, require Chrome and have the installer install it as a hard prereq. |
| A5 | External-ATS sites (Greenhouse, Lever, Workable, Ashby, Personio) do not aggressively probe for CDP automation the way linkedin.com does. | Run external_ats.apply against one real Greenhouse + one real Lever + one Workable form (logging-only, abort before submit) and check for CAPTCHA / interstitial. | If a vendor blocks, add that vendor's detection to the EXTERNAL_APPLY classifier so we route those to manual. |
| A6 | Sidegig's LinkedIn JobSpy scrape from a Hamburg residential IP at the configured volume (3–5 search terms × 15 results, daily) stays under LinkedIn's rate-limit threshold. | Operator runs the existing sidegig daily.yml workflow manually from her home IP for 7 days, checks `source_runs.error` for any 429 / 403. | If throttled: drop to 2 terms × 10 results, increase `sleep_jitter`, or skip LinkedIn discovery and rely only on Indeed. |
| A7 | The `apply_method` two-stage probe's worst case (probe at apply time, find Easy Apply, abort) counts against the 10/day apply cap or not? Spec says it doesn't — the cap is on completed submissions only. | Implementation reads cap from `submissions` table, not `apply_requests` table. Phase 4 has a unit test covering this. | n/a — this is a self-imposed constraint, not external. |
| A8 | ~~Briefcase can register a Windows Task Scheduler task as part of its install step.~~ **VERIFIED via Briefcase docs + WebSearch results.** Briefcase 0.3.25+ supports MSI post-install + pre-uninstall scripts via WiX 5.0.2. Path: post-install script runs `schtasks /create /XML JobscoutDiscover.xml /TN "Jobscout Discover"` and `schtasks /create /XML JobscoutApplyWorker.xml /TN "Jobscout Apply Worker"`; pre-uninstall script runs `schtasks /delete /TN ... /F` for both. The pre-uninstall cleanup is **mandatory** — Briefcase docs note MSI "clean state" obligations: anything created by post-install must be reverted by pre-uninstall or the MSI registry becomes inconsistent. Briefcase exposes `INSTALLER_PATH` env var to scripts. | — | — |

## 11. Sequenced milestones (no time estimates per org policy)

1. **Phase 0 — fixture corpus + classifier tests.** Capture LinkedIn + Indeed payloads (≥30 each), hand-label, build `derive.py` against tests. Gate: classifier ≥95% accurate on labelled set.
2. **Phase 1 — sources + filters + scoring + drafting.** Port `linkedin.py`, add `indeed.py`. Wire `derive.py` into the pipeline. Inverted filters (drop part-time/contract). Carry score+draft from sidegig. Gate: end-to-end smoke against fixtures passes.
3. **Phase 2 — schema + Supabase.** Apply migrations, create `profiles` table, populate from operator-side bootstrap script against test user.
4. **Phase 3 — Streamlit UI.** Adapt sidegig's `app.py`: drop Onboarding/Observability tabs, add Settings tab driven by `profiles`, hidden `/admin` route. Pipeline tab shows EXTERNAL_APPLY auto-apply and EASY_APPLY manual flows differently.
5. **Phase 4 — apply pipeline restricted to external ATS.** Port `worker.py` and `external_ats.py`. Wire 10/day cap and `apply_method == EXTERNAL_APPLY` filter into queue claim logic.
6. **Phase 5 — Windows installer + Task Scheduler.** `chrome-cdp.bat`, `apply-worker.bat`, `discover.bat`, Task Scheduler XML, Briefcase installer. Test on operator's physical Windows laptop.
7. **Phase 6 — operator handover.** Bootstrap user's profile, run installer on user's PC, walk through dashboard.

## 12. References

- Sidegig source (`/Users/izabelcvetkovic/projects/sidegig/`) — primary reference for ported code.
- Sidegig's existing apply path: `sidegig/apply/{worker,external_ats}.py`, `scripts/{chrome-cdp,apply-worker-local}.sh`, `com.sidegig.apply-worker.plist`.
- Filter validation precedent: [feedback_test_filters_against_real_data](../../../../../.claude/projects/-Users-izabelcvetkovic-projects-sidegig/memory/feedback_test_filters_against_real_data.md).
- LinkedIn 2026 enforcement: [Syntora 2026 guide](https://syntora.io/solutions/linkedin-automation-without-the-ban-risk---whats-actually-working-in-2026), [GetSales 2026 guide](https://getsales.io/blog/linkedin-automation-safety-guide-2026/).
- CDP detection: [Castle.io](https://blog.castle.io/how-to-detect-headless-chrome-bots-instrumented-with-playwright/), [Rebrowser](https://rebrowser.net/blog/how-to-fix-runtime-enable-cdp-detection-of-puppeteer-playwright-and-other-automation-libraries).
- JobSpy + LinkedIn IP behavior: [Proxies.sx 2026 guide](https://www.proxies.sx/blog/linkedin-proxy-automation-guide-2026).
- Windows Task Scheduler patterns: [Dev|Journal May 2026](https://earezki.com/ai-news/2026-05-14-python-task-scheduler-run-any-script-automatically-no-cron-needed/).

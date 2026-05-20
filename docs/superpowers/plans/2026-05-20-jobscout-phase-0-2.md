# jobscout Phases 0–2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Note:** This file is a local working artifact per the user's `no-commit-specs-or-plans` convention. Do not commit.

**Goal:** Deliver a working end-to-end discovery+score+draft data backbone for the jobscout project (Hamburg-only LinkedIn + Indeed listings, classifier-validated arrangement/job_type/apply_method, written to a fresh Supabase Cloud DB), runnable on operator's Mac. No UI / no apply / no installer in this plan — those are Phase 3–6, deferred to follow-up plans.

**Architecture:** Fork sidegig into a new `jobscout` repo. Strip Upwork / freelancermap / Bundesagentur. Add fixture-driven classifiers for the three derived fields the original sidegig filter missed. Invert sidegig's filter (drop part-time/contract, keep full-time/permanent). Use JobSpy's `company_url_direct` as the apply-method signal. Write to a new Supabase project; profile lives in a DB table, not YAML, so a non-tech end user can edit it later via the UI (Phase 3).

**Tech Stack:** Python 3.13, Poetry, Pydantic v2, JobSpy, Playwright (only for the Phase 4+ apply path — not in this plan's scope), Supabase Python SDK, Gemini Flash Lite via google-genai, sentence-transformers, ruff, mypy strict, pytest.

**Reference spec:** `docs/superpowers/specs/2026-05-20-jobscout-design.md`.

---

## Execution policy (read before dispatching any subagent)

These rules override any sidegig precedent — they apply to every task in this plan and any follow-up plans.

### Model selection
- **Default to Opus 4.7** for every subagent dispatch. Set `model: "opus"` on every `Agent` call.
- **Sonnet 4.6 only for genuinely trivial tasks** — mechanical renames, copy-paste-with-substitution, file moves. Be the exception, not the rule.
- **NEVER Haiku.** The user has excluded it.

### Code style — cleaner than sidegig
- **No essay-length comments.** Sidegig has lots (e.g. `external_ats.py` top, `linkedin.py`'s rate-parsing block). When porting, strip them. Keep only one short line where the WHY is genuinely non-obvious.
- **No verbose docstrings.** One line max, only on public APIs whose name doesn't already explain them.
- **No defensive checks for impossible cases.** Trust the data layer.
- **Simpler is better.** When in doubt between two implementations, pick the shorter one.
- **Reuse what works from sidegig.** Don't re-derive solved problems — but port them *cleaner* than the original.

### Testing — after every implementation task
- After every task, run the unit tests touched by the change + the integration smoke. They must pass before the commit step.
- Once the Streamlit dashboard is up (Phase 3+, separate plan), every UI task ends with **Playwright MCP verification**: navigate to the Streamlit URL via `mcp__plugin_playwright_playwright__browser_navigate`, snapshot, assert structure, click through critical flows. Unit tests alone don't catch Streamlit state-reactivity bugs.
- For this plan's data-layer scope (no UI yet), the equivalent verification is a manual `make discover && make filter && make score` against the real Supabase + 5-listing limit at the end of each phase.

---

## File structure (created or modified in this plan)

```
jobscout/                                # NEW REPO, sibling of sidegig/
├── README.md                            # adapted from sidegig
├── pyproject.toml                       # adapted: drop weasyprint, upwork-related deps
├── poetry.lock
├── Makefile                             # adapted
├── .env.example
├── .gitignore
│
├── config/
│   ├── spam_rules.yaml                  # carried verbatim from sidegig
│   └── prompts/
│       ├── score.v1.md                  # carried
│       ├── draft_proposal.v1.md         # carried
│       └── draft_cv.v1.md               # carried
│
├── jobscout/
│   ├── __init__.py
│   ├── models.py                        # ADAPTED: Source enum = linkedin/indeed; add ApplyMethod, Arrangement, JobType enums
│   ├── db.py                            # ADAPTED: profiles CRUD, drop onboarding/upwork
│   ├── llm.py                           # carried verbatim
│   ├── config_loader.py                 # REWRITTEN: load profile from DB row, not YAML
│   ├── embeddings.py                    # carried
│   ├── filters.py                       # ADAPTED: inverted job_type filter, arrangement filter
│   ├── derive.py                        # NEW: arrangement / job_type / apply_method classifiers
│   ├── discover.py                      # ADAPTED: only linkedin + indeed sources
│   ├── score.py                         # carried
│   ├── draft.py                         # ADAPTED: reads from `profiles` row instead of YAML
│   ├── freshness.py                     # carried
│   ├── screener.py                      # carried
│   └── sources/
│       ├── __init__.py
│       ├── base.py                      # carried
│       ├── linkedin.py                  # ADAPTED: derive apply_method from company_url_direct
│       └── indeed.py                    # NEW
│
├── supabase/
│   ├── config.toml                      # carried
│   └── migrations/
│       ├── 20260520120000_initial_schema.sql   # NEW: sidegig schema with deltas
│       └── 20260520120100_profiles.sql         # NEW
│
├── scripts/
│   ├── capture_fixtures.py              # NEW: pulls real LinkedIn/Indeed payloads to tests/fixtures
│   ├── label_fixtures.py                # NEW: opens labels.json template per fixture for operator to fill
│   └── bootstrap_profile_from_linkedin.py   # NEW: operator-run, populates profiles row
│
└── tests/
    ├── conftest.py                      # NEW: shared fixtures (test profile, fake LLM)
    ├── fixtures/
    │   └── listings/
    │       ├── linkedin/                # ≥30 .json + .labels.json pairs
    │       └── indeed/                  # ≥30 .json + .labels.json pairs
    ├── test_derive_arrangement.py       # NEW
    ├── test_derive_job_type.py          # NEW
    ├── test_derive_apply_method.py      # NEW
    ├── test_filters.py                  # NEW: covers inverted filter rules
    ├── test_sources_linkedin.py         # NEW
    ├── test_sources_indeed.py           # NEW
    └── test_db_profiles.py              # NEW
```

---

## Task 0: Fork sidegig → jobscout repo, scrub unused sources

**Files:**
- Create: `~/projects/jobscout/` (new repo at sibling of sidegig)

**Why first:** Everything downstream assumes a clean repo without Upwork/freelancermap/Bundesagentur code. Doing this in a single early task means later tasks never reference modules that shouldn't exist.

- [ ] **Step 1: Create the new repo via cp + git init**

```bash
cp -R /Users/izabelcvetkovic/projects/sidegig /Users/izabelcvetkovic/projects/jobscout
cd /Users/izabelcvetkovic/projects/jobscout
rm -rf .git .venv .pytest_cache .mypy_cache .ruff_cache sentence_transformers_cache
rm -f *.png *.jpeg portfolio_*.yaml sidegig_*.jpeg freudian_state.yaml sidegig_thumb_dialog.yaml i_rene_thumb.jpeg icis2023_*.jpeg
git init
git add -A
git status | head -40
```

Expected: lots of `new file:` entries, no `.git` dir, no caches.

- [ ] **Step 2: Rename package directory**

```bash
cd /Users/izabelcvetkovic/projects/jobscout
git mv sidegig jobscout
```

- [ ] **Step 3: Delete unused source modules**

```bash
cd /Users/izabelcvetkovic/projects/jobscout
git rm jobscout/sources/upwork.py jobscout/sources/bundesagentur.py jobscout/sources/freelancermap.py
git rm jobscout/apply/upwork.py jobscout/apply/freelancermap.py
git rm scripts/upwork-discover-local.sh scripts/test_external_ats.sh scripts/com.sidegig.upwork-discover.plist scripts/migrate_local_to_cloud.py scripts/seed_onboarding.py
git rm -r config/onboarding_seed.yaml docs/specs docs/plans docs/snippets 2>/dev/null || true
git rm config/profile.yaml config/profile_photo.jpg config/cv_base_*.md 2>/dev/null || true
```

- [ ] **Step 4: Update `jobscout/__init__.py` and rename internal imports**

```bash
cd /Users/izabelcvetkovic/projects/jobscout
# Sed every `from sidegig.` → `from jobscout.`
find jobscout tests scripts -type f -name '*.py' -exec sed -i '' 's/from sidegig/from jobscout/g; s/import sidegig/import jobscout/g' {} +
```

Verify nothing left referencing sidegig in Python:
```bash
grep -rn "sidegig" jobscout tests scripts --include='*.py' | head -10
```

Expected: empty.

- [ ] **Step 5: Update `pyproject.toml`**

Replace the `[project]` block to read:

```toml
[project]
name = "jobscout"
version = "0.1.0"
description = "Hamburg-region full-time job discovery + AI drafting for a non-technical user"
authors = [
    {name = "Izabel Cvetkovic", email = "izabelcvetkovic@gmail.com"}
]
readme = "README.md"
requires-python = ">=3.13,<4.0"
dependencies = [
    "pydantic (>=2.9,<3.0)",
    "python-dotenv (>=1.0,<2.0)",
    "supabase (>=2.9,<3.0)",
    "anthropic (>=0.40,<0.41)",
    "feedparser (>=6.0,<7.0)",
    "beautifulsoup4 (>=4.12,<5.0)",
    "lxml (>=5.3,<6.0)",
    "httpx (>=0.27,<0.28)",
    "pyyaml (>=6.0,<7.0)",
    "jinja2 (>=3.1,<4.0)",
    "markdown (>=3.7,<4.0)",
    "streamlit (>=1.40,<2.0)",
    "python-jobspy (>=1.1,<2.0)",
    "lingua-language-detector (>=2.0,<3.0)",
    "sentence-transformers (>=3.3,<4.0)",
    "google-genai (>=1.0,<2.0)",
    "playwright (>=1.59.0,<2.0.0)",
    "playwright-stealth (>=2.0.3,<3.0.0)",
    "notifypy (>=0.3,<0.4)",
    "pypdf (>=4.0,<5.0)"
]
```

Drop: `weasyprint`, `pyperclip`, `crawl4ai` (not needed in Phase 0–2 scope).
Add: `notifypy` (cross-platform notifications), `pypdf` (for CV bootstrap in Phase 2).

Also update `[tool.poetry] package-mode = false` line to keep the same. Update `[tool.mypy.overrides]` removing the `weasyprint` and `pyperclip` overrides.

- [ ] **Step 6: Regenerate lockfile**

```bash
cd /Users/izabelcvetkovic/projects/jobscout
rm poetry.lock
poetry lock --no-update 2>&1 | tail -20
```

Expected: "Resolving dependencies... Done"

- [ ] **Step 7: Verify install works**

```bash
poetry install --no-interaction 2>&1 | tail -10
```

Expected: install completes without error.

- [ ] **Step 8: Update Makefile**

Open `Makefile` and:
- replace `sidegig` with `jobscout` everywhere
- delete the `seed:` target (no onboarding seed)
- delete any `upwork` references

Verify:
```bash
grep -n "sidegig\|upwork\|seed" Makefile
```

Expected: empty.

- [ ] **Step 9: Update README.md**

Replace contents with:

```markdown
# jobscout

Hamburg-region full-time job discovery + AI drafting for a non-technical end user.
Forked from `sidegig` with these material differences:

- Sources: LinkedIn + Indeed only (no Upwork / Bundesagentur / freelancermap)
- Roles: full-time / permanent only (sidegig was freelance / contract)
- Geography: Hamburg only
- Apply: external-ATS only, never LinkedIn Easy Apply
- UI consumer: a non-technical end user on Windows (Phase 3+)
- Profile: stored in DB, not YAML

See `docs/superpowers/specs/2026-05-20-jobscout-design.md` for the design.
```

- [ ] **Step 10: First commit**

```bash
cd /Users/izabelcvetkovic/projects/jobscout
git add -A
git commit -m "chore: fork sidegig → jobscout, strip Upwork/Bundesagentur/freelancermap"
```

Expected: commit succeeds. `git log --oneline | head -3` shows the new commit.

---

## Task 1: Wire up new Supabase project for jobscout

**Files:**
- Modify: `.env` (operator-only, not committed)
- Verify: `jobscout/db.py:_client()` works against the new project

**Why now:** The fixture-capture and classifier-test work doesn't need Supabase, but having the DB in place means later tasks can write straight to it without re-wiring. We don't apply migrations yet — that's Task 12.

- [ ] **Step 1: Create new Supabase project (manual, operator action)**

Operator opens https://supabase.com/dashboard, clicks "New project", names it `jobscout`, region EU Central (Frankfurt), strong DB password (stored in 1Password). Wait until provisioned.

- [ ] **Step 2: Copy URL + service_role key into `.env`**

```bash
cd /Users/izabelcvetkovic/projects/jobscout
cp .env.example .env
```

Edit `.env`:
```
SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service_role_key_from_settings_api>
SUPABASE_ANON_KEY=<anon_key>
GEMINI_API_KEY=<carry over from sidegig .env>
LLM_PROVIDER=gemini
SCRAPER_CONTACT_EMAIL=izabelcvetkovic@gmail.com
```

Update `.env.example` to mirror (with values redacted), commit `.env.example` only.

- [ ] **Step 3: Smoke-test client construction**

```bash
poetry run python -c "from jobscout.db import _client; c = _client(); print(c.url)"
```

Expected: prints your supabase URL. No exceptions.

If it fails (e.g. "SUPABASE_URL not set"), check `.env` is in repo root and `python-dotenv` is loading it (it's loaded by `db.py` via `os.environ` after `dotenv` runs — sidegig pattern).

- [ ] **Step 4: Commit `.env.example` only**

```bash
git add .env.example
git commit -m "chore: add jobscout supabase env template"
```

---

## Task 2: New `Arrangement`, `JobType`, `ApplyMethod` enums in models.py

**Files:**
- Modify: `jobscout/models.py`
- Test: `tests/test_models.py` (NEW)

- [ ] **Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
from jobscout.models import Arrangement, ApplyMethod, JobType, Source, Listing


def test_source_enum_restricted_to_linkedin_indeed():
    assert {s.value for s in Source} == {"linkedin", "indeed"}


def test_arrangement_enum():
    assert Arrangement.REMOTE.value == "remote"
    assert Arrangement.HYBRID.value == "hybrid"
    assert Arrangement.ONSITE.value == "onsite"
    assert Arrangement.UNKNOWN.value == "unknown"


def test_job_type_enum():
    assert JobType.FULLTIME.value == "fulltime"
    assert JobType.PERMANENT.value == "permanent"
    assert JobType.CONTRACT.value == "contract"
    assert JobType.PARTTIME.value == "parttime"
    assert JobType.INTERN.value == "intern"
    assert JobType.UNKNOWN.value == "unknown"


def test_apply_method_enum():
    assert ApplyMethod.EXTERNAL_APPLY.value == "external_apply"
    assert ApplyMethod.EASY_APPLY.value == "easy_apply"


def test_listing_has_new_fields():
    l = Listing(
        source=Source.LINKEDIN,
        source_id="abc",
        url="https://linkedin.com/jobs/view/123",
        title="ML Engineer",
        raw={},
    )
    assert l.arrangement is None
    assert l.job_type_classified is None
    assert l.apply_method is None
    assert l.arrangement_evidence is None
    assert l.job_type_evidence is None
```

- [ ] **Step 2: Run test, verify it fails**

```bash
poetry run pytest tests/test_models.py -v
```

Expected: import errors / attribute errors on `Arrangement`, `JobType`, `ApplyMethod`, and the new Listing fields.

- [ ] **Step 3: Update `jobscout/models.py`**

Replace `Source` enum:

```python
class Source(StrEnum):
    LINKEDIN = "linkedin"
    INDEED = "indeed"
```

Add (before `class Listing`):

```python
class Arrangement(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class JobType(StrEnum):
    FULLTIME = "fulltime"
    PERMANENT = "permanent"
    CONTRACT = "contract"
    PARTTIME = "parttime"
    INTERN = "intern"
    UNKNOWN = "unknown"


class ApplyMethod(StrEnum):
    EXTERNAL_APPLY = "external_apply"
    EASY_APPLY = "easy_apply"
```

Add to `Listing`:

```python
    arrangement: Arrangement | None = None
    arrangement_evidence: str | None = None
    job_type_classified: JobType | None = None
    job_type_evidence: str | None = None
    apply_method: ApplyMethod | None = None
```

Note: name the field `job_type_classified` to avoid clash with the existing `job_type` field on `Listing` (if present from sidegig — verify with `grep`). If sidegig had a `job_type` field, rename to keep both — the JobSpy raw value vs. our classified value are different things.

Remove the sidegig `RateUnit.HOUR / DAY / FIXED / SALARY / UNKNOWN` enum and `rate_*` fields? No — keep them, they're carried over and harmless if always-null.

- [ ] **Step 4: Run test, verify it passes**

```bash
poetry run pytest tests/test_models.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add jobscout/models.py tests/test_models.py
git commit -m "feat(models): add Arrangement / JobType / ApplyMethod enums + Listing fields"
```

---

## Task 3: capture_fixtures.py — pull real LinkedIn + Indeed payloads

**Files:**
- Create: `scripts/capture_fixtures.py`
- Create: `tests/fixtures/listings/linkedin/*.json` (output, ≥30 files)
- Create: `tests/fixtures/listings/indeed/*.json` (output, ≥30 files)

**Why TDD doesn't fit:** This is a one-shot data-collection script. The "test" is that the script produces the expected number of JSON files in the expected layout.

- [ ] **Step 1: Create the capture script**

`scripts/capture_fixtures.py`:

```python
"""Pull real LinkedIn + Indeed payloads into tests/fixtures/listings/ for
classifier validation. Run-once during Phase 0 to seed the corpus.

Hamburg-region search terms cover the breadth of full-time AI/ML/SWE roles
the end user might see; the diversity of arrangement (remote / hybrid /
onsite) and job_type (fulltime / contract / intern) in the corpus is what
makes the classifier tests meaningful.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from jobspy import scrape_jobs

ROOT = Path(__file__).resolve().parent.parent
LINKEDIN_DIR = ROOT / "tests" / "fixtures" / "listings" / "linkedin"
INDEED_DIR = ROOT / "tests" / "fixtures" / "listings" / "indeed"

SEARCH_TERMS = [
    "AI Engineer",
    "Machine Learning Engineer",
    "Software Engineer",
    "Data Scientist",
    "Python Developer",
]


def _safe(d: dict[str, Any]) -> dict[str, Any]:
    """Coerce numpy/pandas scalars to JSON-safe types."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if v is None or isinstance(v, (str, int, float, bool, list, dict)):
            out[str(k)] = v
        else:
            out[str(k)] = str(v)
    return out


def capture(site: str, out_dir: Path, country: str | None = None) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    captured = 0
    for term in SEARCH_TERMS:
        kwargs: dict[str, Any] = {
            "site_name": [site],
            "search_term": term,
            "location": "Hamburg, Germany",
            "results_wanted": 8,
            "hours_old": 168,
            "linkedin_fetch_description": True,
        }
        if country:
            kwargs["country_indeed"] = country
        print(f"[{site}] {term!r} ...", flush=True)
        df = scrape_jobs(**kwargs)
        for _, row in df.iterrows():
            d = _safe(row.to_dict())
            sid = d.get("id") or d.get("job_url") or str(captured)
            slug = str(sid).replace("/", "_").replace(":", "_")[:60]
            fp = out_dir / f"{slug}.json"
            fp.write_text(json.dumps(d, indent=2, ensure_ascii=False))
            captured += 1
    return captured


def main() -> int:
    li = capture("linkedin", LINKEDIN_DIR)
    print(f"LinkedIn captured: {li}")
    ind = capture("indeed", INDEED_DIR, country="germany")
    print(f"Indeed captured: {ind}")
    if li < 30 or ind < 30:
        print("WARNING: target was ≥30 per source — re-run with more terms if too few", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the script**

```bash
cd /Users/izabelcvetkovic/projects/jobscout
mkdir -p tests/fixtures/listings/linkedin tests/fixtures/listings/indeed
poetry run python scripts/capture_fixtures.py
```

Expected: prints per-term progress, ends with "LinkedIn captured: N" and "Indeed captured: M", both ≥30.

If LinkedIn returns fewer than 30 from logged-out scrape, add more search terms (e.g. "Backend Engineer", "Data Engineer", "MLOps", "LLM Engineer") and re-run. The script overwrites existing files with the same source_id, so re-running is safe.

- [ ] **Step 3: Verify the file count**

```bash
ls tests/fixtures/listings/linkedin/ | wc -l
ls tests/fixtures/listings/indeed/ | wc -l
```

Expected: both ≥30.

- [ ] **Step 4: Spot-check one fixture**

```bash
poetry run python -c "
import json, pathlib
files = sorted(pathlib.Path('tests/fixtures/listings/linkedin').glob('*.json'))
print(f'{len(files)} LinkedIn fixtures')
d = json.loads(files[0].read_text())
for k in ('title','company','location','is_remote','job_type','company_url_direct','description'):
    v = d.get(k)
    if isinstance(v, str) and len(v) > 80:
        v = v[:80] + '…'
    print(f'  {k}: {v}')
"
```

Expected: real data — title, company, location, etc. — and **note whether `company_url_direct` is present**. This is the apply_method signal we depend on; if it's null for most LinkedIn listings, that's a finding for Task 7.

- [ ] **Step 5: Commit fixtures**

```bash
git add scripts/capture_fixtures.py tests/fixtures/listings/
git commit -m "feat(fixtures): capture LinkedIn + Indeed payloads for classifier validation"
```

---

## Task 4: label_fixtures.py + manual labelling pass

**Files:**
- Create: `scripts/label_fixtures.py`
- Create: `tests/fixtures/listings/{linkedin,indeed}/*.labels.json` (output, one per fixture)

- [ ] **Step 1: Create the label scaffold script**

`scripts/label_fixtures.py`:

```python
"""For each captured fixture, emit a sibling .labels.json scaffold for
operator-hand-labelling. The classifier tests read these labels and assert
classifier output matches.

Pre-fills suggested labels based on raw signals (best-effort, operator must
verify each one) — saves the operator from typing every field from scratch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DIRS = [
    ROOT / "tests" / "fixtures" / "listings" / "linkedin",
    ROOT / "tests" / "fixtures" / "listings" / "indeed",
]


def _suggest_arrangement(raw: dict[str, Any]) -> str:
    text = " ".join(
        str(raw.get(k) or "") for k in ("title", "description", "location", "work_from_home_type")
    ).lower()
    if any(w in text for w in ("vor ort", "im büro", "fully on-site", "5 days/week in office", "5 days a week in office")):
        return "onsite"
    if any(w in text for w in ("hybrid", "tage im büro", "days in office", "few days in office")):
        return "hybrid"
    if raw.get("is_remote") or any(w in text for w in ("remote", "home office", "fully remote", "100% remote")):
        return "remote"
    return "unknown"


def _suggest_job_type(raw: dict[str, Any]) -> str:
    text = " ".join(str(raw.get(k) or "") for k in ("title", "description", "job_type")).lower()
    if any(w in text for w in ("intern", "praktikum", "werkstudent")):
        return "intern"
    if any(w in text for w in ("part-time", "parttime", "teilzeit")):
        return "parttime"
    if any(w in text for w in ("contract", "freelance", "freiberuflich")):
        return "contract"
    if any(w in text for w in ("permanent", "unbefristet", "festanstellung")):
        return "permanent"
    if any(w in text for w in ("full-time", "fulltime", "vollzeit")):
        return "fulltime"
    return "unknown"


def _suggest_apply_method(raw: dict[str, Any]) -> str:
    return "external_apply" if raw.get("company_url_direct") else "easy_apply"


def main() -> int:
    n = 0
    for d in DIRS:
        if not d.exists():
            continue
        for fp in sorted(d.glob("*.json")):
            if fp.name.endswith(".labels.json"):
                continue
            labels_fp = fp.with_suffix(".labels.json")
            if labels_fp.exists():
                continue
            raw = json.loads(fp.read_text())
            scaffold = {
                "expected_arrangement": _suggest_arrangement(raw),
                "expected_job_type": _suggest_job_type(raw),
                "expected_apply_method": _suggest_apply_method(raw),
                "labeler_notes": "",
                "verified_by_operator": False,
            }
            labels_fp.write_text(json.dumps(scaffold, indent=2, ensure_ascii=False))
            n += 1
    print(f"Created {n} label scaffolds.")
    print("Operator: open each .labels.json, correct the suggested values where wrong,")
    print("set verified_by_operator=true. Classifier tests will fail loudly until")
    print("≥95% of fixtures have verified_by_operator=true.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the scaffold script**

```bash
poetry run python scripts/label_fixtures.py
```

Expected: prints "Created N label scaffolds." where N matches the fixture count.

- [ ] **Step 3: Operator manually verifies labels**

Open each `.labels.json` file, read the corresponding fixture's `title` + `description` + `location` (e.g. with `jq -r .description tests/fixtures/listings/linkedin/abc.json`), correct the suggested label, set `verified_by_operator: true`.

This is the labour-intensive step — budget for a focused session. Aim for ≥30 verified per source.

When done, check the count:
```bash
poetry run python -c "
import json, pathlib
for src in ('linkedin','indeed'):
    d = pathlib.Path(f'tests/fixtures/listings/{src}')
    total = len(list(d.glob('*.labels.json')))
    verified = sum(1 for f in d.glob('*.labels.json') if json.loads(f.read_text()).get('verified_by_operator'))
    print(f'{src}: {verified}/{total} verified')
"
```

Expected: both `linkedin: ≥30/N verified` and `indeed: ≥30/N verified`.

- [ ] **Step 4: Commit labels**

```bash
git add scripts/label_fixtures.py tests/fixtures/listings/
git commit -m "feat(fixtures): hand-labeled arrangement/job_type/apply_method per listing"
```

---

## Task 5: derive.py classifier — `classify_arrangement`

**Files:**
- Create: `jobscout/derive.py`
- Create: `tests/test_derive_arrangement.py`

- [ ] **Step 1: Write the failing test (fixture-driven)**

`tests/test_derive_arrangement.py`:

```python
"""Validates classify_arrangement against the hand-labelled fixture corpus.

Per the feedback_test_filters_against_real_data memory: the filter is
broken until we can show it works on real data. This test IS that proof.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobscout.derive import classify_arrangement

FIXTURE_DIRS = [
    Path(__file__).parent / "fixtures" / "listings" / "linkedin",
    Path(__file__).parent / "fixtures" / "listings" / "indeed",
]


def _verified_pairs():
    for d in FIXTURE_DIRS:
        for raw_fp in sorted(d.glob("*.json")):
            if raw_fp.name.endswith(".labels.json"):
                continue
            labels_fp = raw_fp.with_suffix(".labels.json")
            if not labels_fp.exists():
                continue
            labels = json.loads(labels_fp.read_text())
            if not labels.get("verified_by_operator"):
                continue
            yield raw_fp.name, json.loads(raw_fp.read_text()), labels


def test_classifier_arrangement_against_fixtures():
    pairs = list(_verified_pairs())
    assert len(pairs) >= 60, f"Need ≥60 verified fixtures across sources; have {len(pairs)}"
    correct = 0
    mismatches: list[str] = []
    for name, raw, labels in pairs:
        expected = labels["expected_arrangement"]
        actual_value, _evidence = classify_arrangement(raw)
        if actual_value.value == expected:
            correct += 1
        else:
            mismatches.append(f"  {name}: expected {expected!r}, got {actual_value.value!r}")
    accuracy = correct / len(pairs)
    msg = f"\nArrangement classifier accuracy: {accuracy:.1%} ({correct}/{len(pairs)})"
    if mismatches:
        msg += "\nMismatches:\n" + "\n".join(mismatches[:20])
    assert accuracy >= 0.95, msg
```

- [ ] **Step 2: Run the test, verify it fails**

```bash
poetry run pytest tests/test_derive_arrangement.py -v
```

Expected: `ModuleNotFoundError: No module named 'jobscout.derive'`

- [ ] **Step 3: Write the classifier**

`jobscout/derive.py`:

```python
"""Per-source field classifiers.

Each classifier returns (Enum, evidence_string). Evidence is the literal
substring or signal that determined the classification — stored on the
listing row for auditability when a misclassification is reported.

Vocabulary observed in fixture corpus (refresh via the weekly drift check):
- LinkedIn `is_remote`: bool, populated by JobSpy's heuristic regex
  scan of title/description/location. Often False even for hybrid roles.
- Indeed `work_from_home_type`: str | None, populated only for ~40% of
  listings, values seen: "Hybrid", "Remote", "Temporarily remote".
- LinkedIn/Indeed `job_type`: str | list[str] | None, JobSpy's parsed
  field, values seen: "fulltime", "contract", "parttime", "internship",
  often empty.
- LinkedIn `company_url_direct`: str | None, the off-LinkedIn apply URL
  parsed from the `applyUrl` code block. Presence = EXTERNAL_APPLY.
"""

from __future__ import annotations

import re
from typing import Any

from jobscout.models import ApplyMethod, Arrangement, JobType

_ONSITE_PATTERNS = [
    r"\b5\s*(?:days?|tage)\s*(?:/|per\s+|im\s+|in\s+)?\s*(?:week|wk|woche)",
    r"\bfull\s*[-\s]?(?:time|day)\s+(?:on[-\s]?site|in[-\s]?office)",
    r"\bvollständig\s+vor\s+ort\b",
    r"\b100\s*%\s*(?:on[-\s]?site|vor\s+ort)",
    r"\bno\s+(?:remote|home\s+office)\b",
]

_HYBRID_PATTERNS = [
    r"\bhybrid\b",
    r"\b(?:few|some|2|3|4)\s*(?:days?|tage)\s*(?:/|per\s+|im\s+|in\s+)?\s*(?:week|wk|woche|office|büro)",
    r"\b(?:days?|tage)\s+in\s+(?:the\s+)?(?:office|büro)",
    r"\bteilweise\s+vor\s+ort\b",
]

_REMOTE_PATTERNS = [
    r"\b(?:fully|100\s*%)?\s*remote\b",
    r"\bhome\s*[-\s]?office\b",
    r"\bwork[-\s]?from[-\s]?home\b",
    r"\bortsunabhängig\b",
]


def _haystack(raw: dict[str, Any]) -> str:
    parts = [
        str(raw.get("title") or ""),
        str(raw.get("description") or ""),
        str(raw.get("location") or ""),
        str(raw.get("work_from_home_type") or ""),
    ]
    return " ".join(parts).lower()


def _first_match(patterns: list[str], text: str) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(0)
    return None


def classify_arrangement(raw: dict[str, Any]) -> tuple[Arrangement, str]:
    """Order matters: onsite is the most specific (overrides hybrid keyword
    co-occurrence), hybrid next, remote last. work_from_home_type "Hybrid"
    from Indeed wins over keyword heuristics."""
    wfh = (raw.get("work_from_home_type") or "").strip().lower()
    if wfh == "hybrid":
        return Arrangement.HYBRID, "indeed.work_from_home_type=Hybrid"
    if wfh in ("remote", "temporarily remote"):
        return Arrangement.REMOTE, f"indeed.work_from_home_type={raw['work_from_home_type']}"
    text = _haystack(raw)
    if hit := _first_match(_ONSITE_PATTERNS, text):
        return Arrangement.ONSITE, hit
    if hit := _first_match(_HYBRID_PATTERNS, text):
        return Arrangement.HYBRID, hit
    if hit := _first_match(_REMOTE_PATTERNS, text):
        return Arrangement.REMOTE, hit
    if raw.get("is_remote") is True:
        return Arrangement.REMOTE, "jobspy.is_remote=True"
    return Arrangement.UNKNOWN, ""


def classify_job_type(raw: dict[str, Any]) -> tuple[JobType, str]:
    """Placeholder — filled by Task 6."""
    raise NotImplementedError


def classify_apply_method(raw: dict[str, Any]) -> tuple[ApplyMethod, str]:
    """Placeholder — filled by Task 7."""
    raise NotImplementedError
```

- [ ] **Step 4: Run the test, iterate until ≥95% accuracy**

```bash
poetry run pytest tests/test_derive_arrangement.py -v
```

If accuracy < 95%, read the mismatch list, identify the missing pattern (e.g. "remote-friendly", "Remote im Bereich Deutschland"), add to the appropriate `_*_PATTERNS` list, re-run. Iterate until passing.

If a fixture has a `verified_by_operator` label that *you* now disagree with after seeing the classifier disagree, fix the label (and add a `labeler_notes` entry explaining the change) — but only if reviewing the actual listing makes the label change obvious. Do not "tune the labels to the classifier" — that defeats the purpose.

- [ ] **Step 5: Commit**

```bash
git add jobscout/derive.py tests/test_derive_arrangement.py
git commit -m "feat(derive): arrangement classifier with ≥95% accuracy on fixture corpus"
```

---

## Task 6: derive.py classifier — `classify_job_type`

**Files:**
- Modify: `jobscout/derive.py`
- Create: `tests/test_derive_job_type.py`

- [ ] **Step 1: Write the failing test (same fixture-driven pattern as Task 5)**

`tests/test_derive_job_type.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from jobscout.derive import classify_job_type

FIXTURE_DIRS = [
    Path(__file__).parent / "fixtures" / "listings" / "linkedin",
    Path(__file__).parent / "fixtures" / "listings" / "indeed",
]


def _verified_pairs():
    for d in FIXTURE_DIRS:
        for raw_fp in sorted(d.glob("*.json")):
            if raw_fp.name.endswith(".labels.json"):
                continue
            labels_fp = raw_fp.with_suffix(".labels.json")
            if not labels_fp.exists():
                continue
            labels = json.loads(labels_fp.read_text())
            if not labels.get("verified_by_operator"):
                continue
            yield raw_fp.name, json.loads(raw_fp.read_text()), labels


def test_classifier_job_type_against_fixtures():
    pairs = list(_verified_pairs())
    assert len(pairs) >= 60
    correct = 0
    mismatches: list[str] = []
    for name, raw, labels in pairs:
        expected = labels["expected_job_type"]
        actual_value, _evidence = classify_job_type(raw)
        if actual_value.value == expected:
            correct += 1
        else:
            mismatches.append(f"  {name}: expected {expected!r}, got {actual_value.value!r}")
    accuracy = correct / len(pairs)
    msg = f"\nJob-type classifier accuracy: {accuracy:.1%} ({correct}/{len(pairs)})"
    if mismatches:
        msg += "\nMismatches:\n" + "\n".join(mismatches[:20])
    assert accuracy >= 0.95, msg
```

- [ ] **Step 2: Run, verify it fails**

```bash
poetry run pytest tests/test_derive_job_type.py -v
```

Expected: `NotImplementedError`.

- [ ] **Step 3: Implement `classify_job_type`**

Replace the placeholder in `jobscout/derive.py`:

```python
_INTERN_PATTERNS = [
    r"\b(?:intern(?:ship)?|praktikum|werkstudent)\b",
]

_PARTTIME_PATTERNS = [
    r"\b(?:part[-\s]?time|teilzeit)\b",
    r"\b(?:20|24|25|30)\s*(?:h|hours?|stunden?)\s*/?\s*(?:per\s+|pro\s+)?(?:week|woche)\b",
]

_CONTRACT_PATTERNS = [
    r"\b(?:contract|contractor|freelance|freiberuflich)\b",
    r"\bbefristet\b",
    r"\bfixed[-\s]?term\b",
]

_PERMANENT_PATTERNS = [
    r"\b(?:permanent|unbefristet|festanstellung)\b",
]

_FULLTIME_PATTERNS = [
    r"\b(?:full[-\s]?time|fulltime|vollzeit)\b",
    r"\b40\s*(?:h|hours?|stunden?)\s*/?\s*(?:per\s+|pro\s+)?(?:week|woche)\b",
]


def _normalize_jobspy_job_type(raw: dict[str, Any]) -> str:
    """JobSpy may surface job_type as a string OR a list[str]."""
    jt = raw.get("job_type")
    if isinstance(jt, list):
        return " ".join(str(x) for x in jt).lower()
    return str(jt or "").lower()


def classify_job_type(raw: dict[str, Any]) -> tuple[JobType, str]:
    """Order: intern (most specific) → parttime → contract → permanent → fulltime → unknown.
    JobSpy's structured field beats text scan when populated."""
    jt = _normalize_jobspy_job_type(raw)
    if "intern" in jt:
        return JobType.INTERN, f"jobspy.job_type={raw.get('job_type')!r}"
    if "part" in jt:
        return JobType.PARTTIME, f"jobspy.job_type={raw.get('job_type')!r}"
    if "contract" in jt or "temporary" in jt:
        return JobType.CONTRACT, f"jobspy.job_type={raw.get('job_type')!r}"
    if "permanent" in jt:
        return JobType.PERMANENT, f"jobspy.job_type={raw.get('job_type')!r}"
    if "full" in jt or "fulltime" in jt:
        return JobType.FULLTIME, f"jobspy.job_type={raw.get('job_type')!r}"

    text = _haystack(raw)
    if hit := _first_match(_INTERN_PATTERNS, text):
        return JobType.INTERN, hit
    if hit := _first_match(_PARTTIME_PATTERNS, text):
        return JobType.PARTTIME, hit
    if hit := _first_match(_CONTRACT_PATTERNS, text):
        return JobType.CONTRACT, hit
    if hit := _first_match(_PERMANENT_PATTERNS, text):
        return JobType.PERMANENT, hit
    if hit := _first_match(_FULLTIME_PATTERNS, text):
        return JobType.FULLTIME, hit
    return JobType.UNKNOWN, ""
```

- [ ] **Step 4: Run, iterate to ≥95% accuracy** (same procedure as Task 5)

```bash
poetry run pytest tests/test_derive_job_type.py -v
```

- [ ] **Step 5: Commit**

```bash
git add jobscout/derive.py tests/test_derive_job_type.py
git commit -m "feat(derive): job_type classifier with ≥95% accuracy on fixture corpus"
```

---

## Task 7: derive.py classifier — `classify_apply_method`

**Files:**
- Modify: `jobscout/derive.py`
- Create: `tests/test_derive_apply_method.py`

- [ ] **Step 1: Write the failing test**

`tests/test_derive_apply_method.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from jobscout.derive import classify_apply_method
from jobscout.models import ApplyMethod

FIXTURE_DIRS = [
    Path(__file__).parent / "fixtures" / "listings" / "linkedin",
    Path(__file__).parent / "fixtures" / "listings" / "indeed",
]


def _verified_pairs():
    for d in FIXTURE_DIRS:
        for raw_fp in sorted(d.glob("*.json")):
            if raw_fp.name.endswith(".labels.json"):
                continue
            labels_fp = raw_fp.with_suffix(".labels.json")
            if not labels_fp.exists():
                continue
            labels = json.loads(labels_fp.read_text())
            if not labels.get("verified_by_operator"):
                continue
            yield raw_fp.name, json.loads(raw_fp.read_text()), labels


def test_classifier_apply_method_against_fixtures():
    pairs = list(_verified_pairs())
    assert len(pairs) >= 60
    correct = 0
    mismatches: list[str] = []
    for name, raw, labels in pairs:
        expected = labels["expected_apply_method"]
        actual_value, _evidence = classify_apply_method(raw)
        if actual_value.value == expected:
            correct += 1
        else:
            mismatches.append(f"  {name}: expected {expected!r}, got {actual_value.value!r}")
    accuracy = correct / len(pairs)
    msg = f"\nApply-method classifier accuracy: {accuracy:.1%} ({correct}/{len(pairs)})"
    if mismatches:
        msg += "\nMismatches:\n" + "\n".join(mismatches[:20])
    assert accuracy >= 0.95, msg


def test_classifier_treats_empty_company_url_direct_as_easy_apply():
    assert classify_apply_method({"company_url_direct": None})[0] == ApplyMethod.EASY_APPLY
    assert classify_apply_method({"company_url_direct": ""})[0] == ApplyMethod.EASY_APPLY
    assert classify_apply_method({})[0] == ApplyMethod.EASY_APPLY


def test_classifier_treats_populated_company_url_direct_as_external_apply():
    actual, evidence = classify_apply_method(
        {"company_url_direct": "https://boards.greenhouse.io/foo/jobs/123"}
    )
    assert actual == ApplyMethod.EXTERNAL_APPLY
    assert "greenhouse" in evidence
```

- [ ] **Step 2: Run, verify it fails**

```bash
poetry run pytest tests/test_derive_apply_method.py -v
```

Expected: `NotImplementedError`.

- [ ] **Step 3: Implement `classify_apply_method`**

Replace the placeholder in `jobscout/derive.py`:

```python
def classify_apply_method(raw: dict[str, Any]) -> tuple[ApplyMethod, str]:
    """Presence of company_url_direct (the parsed `applyUrl` from LinkedIn's
    detail page, or Indeed's equivalent) means the apply happens off-platform
    on an external ATS — EXTERNAL_APPLY. Absent means in-platform apply
    (LinkedIn Easy Apply / Indeed Apply) — EASY_APPLY, surfaced for manual."""
    url = (raw.get("company_url_direct") or "").strip()
    if url:
        return ApplyMethod.EXTERNAL_APPLY, url
    return ApplyMethod.EASY_APPLY, ""
```

- [ ] **Step 4: Run, verify it passes**

```bash
poetry run pytest tests/test_derive_apply_method.py -v
```

Expected: all 3 tests pass. If the corpus-driven accuracy test fails, it means the labels suggested by `label_fixtures.py` (which use the same `company_url_direct` heuristic) disagree with operator's verification — investigate the mismatch; usually a fixture where the operator's manual review found a different signal.

- [ ] **Step 5: Commit**

```bash
git add jobscout/derive.py tests/test_derive_apply_method.py
git commit -m "feat(derive): apply_method classifier from company_url_direct presence"
```

---

## Task 8: Adapt sources/linkedin.py — populate derived fields

**Files:**
- Modify: `jobscout/sources/linkedin.py`
- Create: `tests/test_sources_linkedin.py`

- [ ] **Step 1: Write the failing test**

`tests/test_sources_linkedin.py`:

```python
"""Tests LinkedIn adapter using the fixture corpus instead of live scrape.

We can't hit live LinkedIn in unit tests (rate limits, flake), so we
monkeypatch the scrape function to return rows loaded from fixtures, then
assert the resulting Listing objects have apply_method / arrangement /
job_type populated correctly via derive.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from jobscout.models import ApplyMethod, Arrangement, JobType, Source

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "listings" / "linkedin"


def _load_fixtures_as_df() -> pd.DataFrame:
    rows = []
    for fp in sorted(FIXTURE_DIR.glob("*.json")):
        if fp.name.endswith(".labels.json"):
            continue
        rows.append(json.loads(fp.read_text()))
    return pd.DataFrame(rows)


def test_linkedin_source_populates_derived_fields(monkeypatch):
    from jobscout.sources import linkedin as li_mod

    df = _load_fixtures_as_df()
    monkeypatch.setattr(li_mod, "_scrape", lambda **_: df)

    src = li_mod.LinkedInSource(search_terms=["test"], location="Hamburg")
    listings = src.discover()

    assert len(listings) > 0
    assert all(l.source == Source.LINKEDIN for l in listings)
    for l in listings:
        assert l.apply_method in (ApplyMethod.EASY_APPLY, ApplyMethod.EXTERNAL_APPLY), l.url
        assert l.arrangement in tuple(Arrangement), l.url
        assert l.job_type_classified in tuple(JobType), l.url
```

- [ ] **Step 2: Run, verify it fails**

```bash
poetry run pytest tests/test_sources_linkedin.py -v
```

Expected: `AttributeError` on `apply_method` or similar — the adapter hasn't been updated yet.

- [ ] **Step 3: Modify `jobscout/sources/linkedin.py`**

Update the `discover()` method to call the classifiers and populate the new fields. In the existing per-row loop (around line 109 of sidegig's version), after the existing `Listing(...)` construction, replace with:

```python
                from jobscout.derive import (
                    classify_apply_method,
                    classify_arrangement,
                    classify_job_type,
                )

                # Pass the raw dict (not Listing) into classifiers — they
                # need access to JobSpy's structured fields like
                # work_from_home_type that don't survive into Listing.
                arrangement, arr_evidence = classify_arrangement(d)
                jt, jt_evidence = classify_job_type(d)
                am, am_evidence = classify_apply_method(d)

                out.append(
                    Listing(
                        source=Source.LINKEDIN,
                        source_id=str(d.get("id") or d["job_url"]),
                        url=str(d["job_url"]),
                        title=str(d["title"]),
                        description=description,
                        location=str(d.get("location") or ""),
                        remote=bool(d.get("is_remote")),
                        language="en",
                        rate_min=rate_min,
                        rate_max=rate_max,
                        rate_unit=rate_unit,
                        currency=currency,
                        arrangement=arrangement,
                        arrangement_evidence=arr_evidence,
                        job_type_classified=jt,
                        job_type_evidence=jt_evidence,
                        apply_method=am,
                        raw=_safe_raw(d),
                    )
                )
```

Also rename the file's existing internal scrape call to `_scrape` if it isn't already named that (sidegig defines `_scrape` at module level around line 72). Verify with:

```bash
grep -n "^def _scrape" jobscout/sources/linkedin.py
```

Expected: one match around line 72. If the function has a different name, rename it so the test's monkeypatch target matches.

Drop the now-broken `is_company_denylisted` import (it references `linkedin_company_denylist` from sidegig's profile YAML — replaced by `profiles.title_denylist` in Task 12). For now, comment out the denylist call inside `discover()`:

```python
                # Denylist re-introduced in Task 13 from profiles row.
                # if is_company_denylisted(d.get("company")):
                #     continue
```

- [ ] **Step 4: Run, verify it passes**

```bash
poetry run pytest tests/test_sources_linkedin.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add jobscout/sources/linkedin.py tests/test_sources_linkedin.py
git commit -m "feat(sources/linkedin): populate arrangement / job_type / apply_method via derive.py"
```

---

## Task 9: Create sources/indeed.py

**Files:**
- Create: `jobscout/sources/indeed.py`
- Create: `tests/test_sources_indeed.py`

- [ ] **Step 1: Write the failing test**

`tests/test_sources_indeed.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from jobscout.models import ApplyMethod, Arrangement, JobType, Source

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "listings" / "indeed"


def _load_fixtures_as_df() -> pd.DataFrame:
    rows = []
    for fp in sorted(FIXTURE_DIR.glob("*.json")):
        if fp.name.endswith(".labels.json"):
            continue
        rows.append(json.loads(fp.read_text()))
    return pd.DataFrame(rows)


def test_indeed_source_populates_derived_fields(monkeypatch):
    from jobscout.sources import indeed as ind_mod

    df = _load_fixtures_as_df()
    monkeypatch.setattr(ind_mod, "_scrape", lambda **_: df)

    src = ind_mod.IndeedSource(search_terms=["test"], location="Hamburg", country="germany")
    listings = src.discover()

    assert len(listings) > 0
    assert all(l.source == Source.INDEED for l in listings)
    for l in listings:
        assert l.apply_method in (ApplyMethod.EASY_APPLY, ApplyMethod.EXTERNAL_APPLY)
        assert l.arrangement in tuple(Arrangement)
        assert l.job_type_classified in tuple(JobType)
```

- [ ] **Step 2: Run, verify it fails**

```bash
poetry run pytest tests/test_sources_indeed.py -v
```

Expected: `ModuleNotFoundError: No module named 'jobscout.sources.indeed'`.

- [ ] **Step 3: Create `jobscout/sources/indeed.py`**

```python
"""Indeed search scraper, JobSpy-backed.

Hamburg-region only. JobSpy supports Indeed via its mobile API, which
doesn't require a logged-in session. work_from_home_type is the Indeed-
specific signal for arrangement (Hybrid / Remote / Temporarily remote) —
when populated, classify_arrangement prefers it over text heuristics.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd
from jobspy import scrape_jobs

from jobscout.derive import (
    classify_apply_method,
    classify_arrangement,
    classify_job_type,
)
from jobscout.models import Listing, RateUnit, Source
from jobscout.sources.base import BRAND_UA, CadenceRule, SourceAdapter

_JSON_SAFE_TYPES = (str, int, float, bool, list, dict, type(None))


def _scrape(**kwargs: Any) -> pd.DataFrame:
    return scrape_jobs(**kwargs)


def _safe_raw(d: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for k, v in d.items():
        safe[str(k)] = v if isinstance(v, _JSON_SAFE_TYPES) else str(v)
    return safe


class IndeedSource(SourceAdapter):
    source = Source.INDEED

    def __init__(
        self,
        search_terms: list[str],
        location: str = "Hamburg, Germany",
        country: str = "germany",
    ) -> None:
        self.search_terms = search_terms
        self.location = location
        self.country = country
        self.policy = CadenceRule(jitter_pct=40.0, ua=BRAND_UA, max_results_per_run=15)

    def discover(self) -> list[Listing]:
        out: list[Listing] = []
        for term in self.search_terms:
            df = _scrape(
                site_name=["indeed"],
                search_term=term,
                location=self.location,
                country_indeed=self.country,
                results_wanted=self.policy.max_results_per_run or 15,
                hours_old=72,
            )
            for _, row in df.iterrows():
                d: dict[str, Any] = row.to_dict()
                description = str(d.get("description") or "")
                arrangement, arr_evidence = classify_arrangement(d)
                jt, jt_evidence = classify_job_type(d)
                am, am_evidence = classify_apply_method(d)
                out.append(
                    Listing(
                        source=Source.INDEED,
                        source_id=str(d.get("id") or d["job_url"]),
                        url=str(d["job_url"]),
                        title=str(d["title"]),
                        description=description,
                        location=str(d.get("location") or ""),
                        remote=bool(d.get("is_remote")),
                        language=None,
                        rate_min=None,
                        rate_max=None,
                        rate_unit=RateUnit.UNKNOWN,
                        currency=None,
                        arrangement=arrangement,
                        arrangement_evidence=arr_evidence,
                        job_type_classified=jt,
                        job_type_evidence=jt_evidence,
                        apply_method=am,
                        raw=_safe_raw(d),
                    )
                )
            self.sleep_jitter(3.0)
        return out
```

- [ ] **Step 4: Run, verify it passes**

```bash
poetry run pytest tests/test_sources_indeed.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add jobscout/sources/indeed.py tests/test_sources_indeed.py
git commit -m "feat(sources/indeed): JobSpy-backed Indeed adapter for Hamburg with derive.py wiring"
```

---

## Task 10: Invert filters.py — drop part-time/contract/intern, keep full-time/permanent

**Files:**
- Modify: `jobscout/filters.py`
- Create: `tests/test_filters.py`

- [ ] **Step 1: Write the failing test**

`tests/test_filters.py`:

```python
"""Filter rules per the spec:
- DROP if job_type_classified ∈ {CONTRACT, PARTTIME, INTERN}
- DROP if arrangement == ONSITE and evidence is high-confidence (literal "5 days/week in office" etc.)
- DROP if title matches profile.title_denylist substrings
- KEEP rate-absent listings (full-time DE listings often omit salary)
"""

from __future__ import annotations

from jobscout.filters import pass_structural
from jobscout.models import (
    ApplyMethod,
    Arrangement,
    JobType,
    Listing,
    Source,
)


def _listing(**overrides):
    base = dict(
        source=Source.LINKEDIN,
        source_id="x",
        url="https://linkedin.com/jobs/view/1",
        title="ML Engineer",
        description="some description",
        location="Hamburg",
        raw={},
        arrangement=Arrangement.REMOTE,
        job_type_classified=JobType.FULLTIME,
        apply_method=ApplyMethod.EXTERNAL_APPLY,
    )
    base.update(overrides)
    return Listing(**base)


def test_drop_contract():
    l = _listing(job_type_classified=JobType.CONTRACT)
    assert pass_structural(l) is False


def test_drop_parttime():
    l = _listing(job_type_classified=JobType.PARTTIME)
    assert pass_structural(l) is False


def test_drop_intern():
    l = _listing(job_type_classified=JobType.INTERN)
    assert pass_structural(l) is False


def test_keep_fulltime():
    l = _listing(job_type_classified=JobType.FULLTIME)
    assert pass_structural(l) is True


def test_keep_permanent():
    l = _listing(job_type_classified=JobType.PERMANENT)
    assert pass_structural(l) is True


def test_drop_high_confidence_onsite():
    l = _listing(
        arrangement=Arrangement.ONSITE,
        arrangement_evidence="5 days/week in office",
    )
    assert pass_structural(l) is False


def test_keep_hybrid():
    l = _listing(arrangement=Arrangement.HYBRID, arrangement_evidence="hybrid")
    assert pass_structural(l) is True


def test_keep_unknown_arrangement():
    l = _listing(arrangement=Arrangement.UNKNOWN, arrangement_evidence="")
    assert pass_structural(l) is True


def test_keep_listing_with_no_rate_data():
    l = _listing(rate_min=None, rate_max=None)
    assert pass_structural(l) is True
```

- [ ] **Step 2: Run, verify it fails**

```bash
poetry run pytest tests/test_filters.py -v
```

Expected: most or all tests fail because the existing sidegig `pass_structural` has the inverted logic (drops full-time).

- [ ] **Step 3: Rewrite `pass_structural` in `jobscout/filters.py`**

Replace the function entirely (the regexes and helpers above it can stay; rename `_FULLTIME_LITERAL_RE` etc. — they're no longer wired in since we use `job_type_classified` instead). Replace `pass_structural`:

```python
_HIGH_CONFIDENCE_ONSITE_EVIDENCE = (
    "5 days",
    "5 tage",
    "100% on-site",
    "100% vor ort",
    "fully on-site",
    "vollständig vor ort",
    "no remote",
)


def pass_structural(listing: Listing) -> bool:
    """Drop part-time/contract/intern. Drop fully-on-site. Keep everything
    else. Skill match, title denylist, embedding match handled by other
    functions; this is only the structural shape."""

    # Job type — we want full-time / permanent only.
    if listing.job_type_classified in (JobType.CONTRACT, JobType.PARTTIME, JobType.INTERN):
        return False

    # Arrangement — drop fully-on-site when classifier is confident.
    if listing.arrangement == Arrangement.ONSITE:
        ev = (listing.arrangement_evidence or "").lower()
        if any(marker in ev for marker in _HIGH_CONFIDENCE_ONSITE_EVIDENCE):
            return False

    return True
```

Update imports at top of the file:

```python
from jobscout.models import (
    Arrangement,
    JobType,
    Listing,
)
```

Drop the `Decimal`, `RateUnit`, `Source` imports if they're no longer referenced (`grep -n` to confirm).

Also drop the now-unused `_FULLTIME_LITERAL_RE`, `_HOURS_PER_WEEK_RE`, `_ACCEPTED_LINKEDIN_JOB_TYPES`, `_AUSLASTUNG_RE`, `_AUSLASTUNG_REFERENCE_HOURS`, and `is_company_denylisted` references. These were sidegig's freelance-side logic and don't apply.

- [ ] **Step 4: Run, verify it passes**

```bash
poetry run pytest tests/test_filters.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Run the full test suite as a regression check**

```bash
poetry run pytest -q
```

Expected: all tests still pass. If older tests broke, they probably relied on the old filter behaviour — update them to use the new enum-based fields.

- [ ] **Step 6: Commit**

```bash
git add jobscout/filters.py tests/test_filters.py
git commit -m "feat(filters): invert structural filter — drop part-time/contract/intern, drop fully-on-site"
```

---

## Task 11: Adapt discover.py — drop dead sources

**Files:**
- Modify: `jobscout/discover.py`

- [ ] **Step 1: Inspect current source registry**

```bash
grep -n "upwork\|bundesagentur\|freelancermap\|LinkedInSource\|IndeedSource" jobscout/discover.py
```

- [ ] **Step 2: Remove dead source branches**

Open `jobscout/discover.py`, delete any import of `upwork`, `bundesagentur`, `freelancermap` source modules. Replace the source-selection map with:

```python
from jobscout.sources.indeed import IndeedSource
from jobscout.sources.linkedin import LinkedInSource

_SOURCES = {
    "linkedin": LinkedInSource,
    "indeed": IndeedSource,
}
```

Update any CLI arg validation (e.g. the `--only` choices) to only allow `linkedin` and `indeed`.

- [ ] **Step 3: Verify the module imports cleanly**

```bash
poetry run python -c "from jobscout.discover import _SOURCES; print(list(_SOURCES))"
```

Expected: `['linkedin', 'indeed']`.

- [ ] **Step 4: Smoke-run discover (manual)**

```bash
poetry run python -m jobscout.discover --only linkedin --limit 3
```

Expected: prints discovery progress, may or may not actually persist depending on Supabase migration state (migrations applied in Task 12) — that's OK for this smoke. Stops without error.

If the run errors on `listings` table missing, ignore; it just means we haven't applied migrations yet. Capture the trace if anything else fails.

- [ ] **Step 5: Commit**

```bash
git add jobscout/discover.py
git commit -m "feat(discover): restrict to linkedin + indeed sources"
```

---

## Task 12: Initial schema migration

**Files:**
- Create: `supabase/migrations/20260520120000_initial_schema.sql`
- Delete: `supabase/migrations/20260513000000_initial_schema.sql`, `20260519120000_apply_requests.sql`

**Why timestamp 20260520120000:** New project, fresh history — we collapse sidegig's two migrations into one initial migration with the deltas baked in, rather than preserving sidegig's history.

- [ ] **Step 1: Delete sidegig's migrations**

```bash
cd /Users/izabelcvetkovic/projects/jobscout
git rm supabase/migrations/*.sql
```

- [ ] **Step 2: Create the new initial migration**

`supabase/migrations/20260520120000_initial_schema.sql`:

```sql
create extension if not exists "pgcrypto";

create table listings (
  id                     uuid primary key default gen_random_uuid(),
  source                 text not null check (source in ('linkedin','indeed')),
  source_id              text not null,
  url                    text not null,
  title                  text not null,
  description            text,
  location               text,
  remote                 boolean,
  language               text,
  rate_min               numeric,
  rate_max               numeric,
  rate_unit              text,
  currency               text,
  hours_per_week         numeric,
  duration_weeks         numeric,
  posted_at              timestamptz,
  discovered_at          timestamptz not null default now(),
  raw                    jsonb not null,
  score                  smallint,
  score_rationale        text,
  spam_score             smallint,
  status                 text not null default 'new',
  arrangement            text check (arrangement in ('remote','hybrid','onsite','unknown')),
  arrangement_evidence   text,
  job_type_classified    text check (job_type_classified in ('fulltime','permanent','contract','parttime','intern','unknown')),
  job_type_evidence      text,
  apply_method           text check (apply_method in ('external_apply','easy_apply')),
  unique (source, source_id)
);
create index on listings (status, score desc nulls last);
create index on listings (discovered_at desc);
create index on listings (apply_method, status);

create table drafts (
  id              uuid primary key default gen_random_uuid(),
  listing_id      uuid not null references listings(id) on delete cascade,
  language        text not null,
  subject         text,
  body            text not null,
  adapted_cv      text,
  model           text not null,
  prompt_version  text not null,
  created_at      timestamptz not null default now()
);
create index on drafts (listing_id, created_at desc);

create table submissions (
  id              uuid primary key default gen_random_uuid(),
  listing_id      uuid not null references listings(id),
  draft_id        uuid references drafts(id),
  submitted_at    timestamptz not null default now(),
  channel         text not null,
  response_status text not null default 'pending',
  response_at     timestamptz,
  notes           text
);
create index on submissions (response_status, submitted_at desc);

create table source_runs (
  id              bigserial primary key,
  source          text not null,
  started_at      timestamptz not null default now(),
  finished_at     timestamptz,
  listings_found  integer,
  listings_new    integer,
  error           text
);
create index on source_runs (source, started_at desc);

-- apply_requests intentionally NOT created in this migration —
-- introduced in Phase 4 (apply pipeline) plan.
-- onboarding_targets intentionally NOT created — out of scope.
```

- [ ] **Step 3: Apply the migration via Supabase CLI**

```bash
cd /Users/izabelcvetkovic/projects/jobscout
supabase link --project-ref <your-project-ref>   # if not already linked
supabase db push
```

Expected: "Applying migration 20260520120000_initial_schema.sql... Done."

If the CLI isn't installed, install via `brew install supabase/tap/supabase` or apply manually via the SQL editor in the Supabase web dashboard.

- [ ] **Step 4: Verify tables exist**

```bash
poetry run python -c "
from jobscout.db import _client
c = _client()
r = c.table('listings').select('id').limit(0).execute()
print('listings OK')
r = c.table('drafts').select('id').limit(0).execute()
print('drafts OK')
r = c.table('submissions').select('id').limit(0).execute()
print('submissions OK')
r = c.table('source_runs').select('id').limit(0).execute()
print('source_runs OK')
"
```

Expected: 4 OK lines.

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/
git commit -m "feat(supabase): initial schema with derived columns, restricted source enum"
```

---

## Task 13: profiles table migration + db.py CRUD

**Files:**
- Create: `supabase/migrations/20260520120100_profiles.sql`
- Modify: `jobscout/db.py`
- Create: `tests/test_db_profiles.py`

- [ ] **Step 1: Write the failing test**

`tests/test_db_profiles.py`:

```python
"""Hits real Supabase — these tests require SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
in env, and run against the new jobscout project. They write & roll back via
linkedin_url uniqueness — re-running is idempotent.
"""

from __future__ import annotations

import os

import pytest

from jobscout.db import _client, get_profile, upsert_profile

TEST_LINKEDIN_URL = "https://www.linkedin.com/in/__jobscout_test_user__/"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    _client().table("profiles").delete().eq("linkedin_url", TEST_LINKEDIN_URL).execute()


@pytest.mark.skipif(not os.environ.get("SUPABASE_URL"), reason="needs supabase")
def test_upsert_and_get_profile():
    upsert_profile(
        {
            "full_name": "Test User",
            "linkedin_url": TEST_LINKEDIN_URL,
            "headline": "ML Engineer",
            "skills": ["Python", "PyTorch"],
            "required_skill_keywords": ["LLM", "RAG"],
            "title_denylist": ["WordPress"],
            "arrangement_preferences": ["remote", "hybrid"],
        }
    )
    p = get_profile(TEST_LINKEDIN_URL)
    assert p is not None
    assert p["full_name"] == "Test User"
    assert "Python" in p["skills"]
    assert "LLM" in p["required_skill_keywords"]
```

- [ ] **Step 2: Run, verify it fails**

```bash
poetry run pytest tests/test_db_profiles.py -v
```

Expected: `relation "public.profiles" does not exist` from PostgREST.

- [ ] **Step 3: Create the migration**

`supabase/migrations/20260520120100_profiles.sql`:

```sql
create table profiles (
  id                       uuid primary key default gen_random_uuid(),
  full_name                text not null,
  email                    text,
  phone                    text,
  linkedin_url             text not null unique,
  location                 text,
  languages                jsonb not null default '{}'::jsonb,
  years_experience         integer,
  headline                 text,
  summary                  text,
  skills                   text[] not null default array[]::text[],
  positions                jsonb not null default '[]'::jsonb,
  education                jsonb not null default '[]'::jsonb,
  target_rate_floor_eur    numeric,
  required_skill_keywords  text[] not null default array[]::text[],
  title_denylist           text[] not null default array[]::text[],
  anchor_summaries         jsonb not null default '[]'::jsonb,
  arrangement_preferences  text[] not null default array['remote','hybrid']::text[],
  cv_markdown              text,
  cv_uploaded_at           timestamptz,
  linkedin_scraped_at      timestamptz,
  updated_at               timestamptz not null default now()
);
```

Apply:
```bash
supabase db push
```

- [ ] **Step 4: Add `get_profile` and `upsert_profile` to `jobscout/db.py`**

At an appropriate point (after the existing helpers), add:

```python
def get_profile(linkedin_url: str) -> dict[str, Any] | None:
    """Returns the single profile row matching linkedin_url, or None."""
    r = _client().table("profiles").select("*").eq("linkedin_url", linkedin_url).execute()
    rows = r.data or []
    return rows[0] if rows else None


def upsert_profile(profile: dict[str, Any]) -> None:
    """Insert or update by linkedin_url. Sets updated_at server-side."""
    payload = dict(profile)
    payload.pop("id", None)
    payload.pop("updated_at", None)
    _client().table("profiles").upsert(payload, on_conflict="linkedin_url").execute()
```

Also remove `list_onboarding_targets`, `update_onboarding_status`, and any other onboarding-related helpers carried from sidegig. Grep:
```bash
grep -n "onboarding" jobscout/db.py
```

For each match, decide: remove if onboarding-related, keep if generic.

- [ ] **Step 5: Run the test, verify it passes**

```bash
poetry run pytest tests/test_db_profiles.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add supabase/migrations/20260520120100_profiles.sql jobscout/db.py tests/test_db_profiles.py
git commit -m "feat(db): profiles table + CRUD helpers; drop onboarding"
```

---

## Task 14: Rewrite config_loader.py — read profile from DB

**Files:**
- Modify: `jobscout/config_loader.py`
- Create: `tests/test_config_loader.py`

**Why:** sidegig's `config_loader.load_profile()` reads `config/profile.yaml`. We deleted that file. Replace with a DB read of the `profiles` row.

- [ ] **Step 1: Inspect current `config_loader.py`**

```bash
cat jobscout/config_loader.py
```

Sidegig's version loads YAML at module-import time and caches. We need a similar shape but reading from DB.

- [ ] **Step 2: Write the failing test**

`tests/test_config_loader.py`:

```python
"""load_profile reads the single profiles row from Supabase. Cached per
process; cache invalidated by clear_profile_cache(). Test inserts a row,
reads, asserts shape — then cleanup.
"""

from __future__ import annotations

import os

import pytest

from jobscout.config_loader import clear_profile_cache, load_profile
from jobscout.db import _client, upsert_profile

TEST_URL = "https://www.linkedin.com/in/__jobscout_test_user_config__/"


@pytest.fixture(autouse=True)
def _cleanup():
    clear_profile_cache()
    yield
    _client().table("profiles").delete().eq("linkedin_url", TEST_URL).execute()
    clear_profile_cache()


@pytest.mark.skipif(not os.environ.get("SUPABASE_URL"), reason="needs supabase")
def test_load_profile_returns_db_row(monkeypatch):
    monkeypatch.setenv("JOBSCOUT_PROFILE_LINKEDIN_URL", TEST_URL)
    upsert_profile(
        {
            "full_name": "Test User",
            "linkedin_url": TEST_URL,
            "required_skill_keywords": ["LLM"],
            "title_denylist": ["WordPress"],
            "arrangement_preferences": ["remote"],
        }
    )
    p = load_profile()
    assert p["full_name"] == "Test User"
    assert p["required_skill_keywords"] == ["LLM"]
    assert p["title_denylist"] == ["WordPress"]
```

- [ ] **Step 3: Run, verify it fails**

```bash
poetry run pytest tests/test_config_loader.py -v
```

Expected: `clear_profile_cache` not defined OR returns a dict from the deleted YAML.

- [ ] **Step 4: Rewrite `jobscout/config_loader.py`**

```python
"""Profile loader.

Reads the single `profiles` row from Supabase. The end user's LinkedIn URL
is configured once via the JOBSCOUT_PROFILE_LINKEDIN_URL env var. Cached
per-process; tests call clear_profile_cache() to force a re-read.

Sidegig read this from config/profile.yaml — that file was deleted in the
fork. End user can edit fields via the Streamlit Settings tab (Phase 3
plan) which round-trips through upsert_profile().
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import yaml

from jobscout.db import get_profile

_SPAM_RULES_PATH = "config/spam_rules.yaml"


def _profile_linkedin_url() -> str:
    url = os.environ.get("JOBSCOUT_PROFILE_LINKEDIN_URL")
    if not url:
        raise RuntimeError(
            "JOBSCOUT_PROFILE_LINKEDIN_URL not set. Run bootstrap_profile_from_linkedin "
            "first, then set this env var to the user's LinkedIn URL."
        )
    return url


@lru_cache(maxsize=1)
def _load_profile_cached() -> dict[str, Any]:
    url = _profile_linkedin_url()
    p = get_profile(url)
    if p is None:
        raise RuntimeError(
            f"No profiles row found for linkedin_url={url!r}. "
            "Run scripts/bootstrap_profile_from_linkedin.py to populate."
        )
    return p


def load_profile() -> dict[str, Any]:
    return _load_profile_cached()


def clear_profile_cache() -> None:
    _load_profile_cached.cache_clear()


@lru_cache(maxsize=1)
def load_spam_rules() -> dict[str, Any]:
    with open(_SPAM_RULES_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
```

- [ ] **Step 5: Run, verify it passes**

```bash
poetry run pytest tests/test_config_loader.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Verify nothing else in the codebase reads the deleted YAML**

```bash
grep -rn "profile.yaml\|profile_photo" jobscout tests scripts --include='*.py'
```

Expected: empty.

- [ ] **Step 7: Commit**

```bash
git add jobscout/config_loader.py tests/test_config_loader.py
git commit -m "refactor(config): load profile from DB instead of YAML"
```

---

## Task 15: bootstrap_profile_from_linkedin.py

**Files:**
- Create: `scripts/bootstrap_profile_from_linkedin.py`

**Why no TDD:** Manual operator script — runs once per new end-user. Verified by inspecting the resulting DB row, not by assertion.

- [ ] **Step 1: Create the bootstrap script**

`scripts/bootstrap_profile_from_linkedin.py`:

```python
"""Bootstrap a new end-user profile by scraping their LinkedIn.

Run-once-per-user by the operator, against operator's logged-in LinkedIn
session in Playwright. Uses LLM to structure the visible page text into
the profiles schema, then upserts to Supabase.

Pre-req: operator must have a Chromium with their LinkedIn login persisted
(re-uses ~/.cache/jobscout/linkedin-profile for the user-data-dir). First
run prompts the operator to log in; subsequent runs re-use the session.

Usage:
    poetry run python scripts/bootstrap_profile_from_linkedin.py \\
        https://www.linkedin.com/in/<the-user>/
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from jobscout.db import upsert_profile
from jobscout.llm import call_json

PROFILE_DIR = Path.home() / ".cache" / "jobscout" / "linkedin-profile"

EXTRACT_PROMPT = """Below is the visible text of a LinkedIn profile page. Extract
the candidate's information as JSON matching this schema. Return ONLY the
JSON, no markdown fences.

Schema:
{
  "full_name": "string",
  "headline": "string",
  "location": "string",
  "summary": "string (the About section)",
  "skills": ["string", ...],
  "positions": [
    {
      "title": "string",
      "company": "string",
      "start": "YYYY-MM or empty",
      "end": "YYYY-MM or 'present' or empty",
      "description": "string"
    }
  ],
  "education": [
    {"degree": "string", "school": "string", "year": "string"}
  ],
  "languages": {"German": "C1", "English": "C2", ...}
}

If a section isn't visible, return an empty string / empty list / empty dict
for that field. Do not invent.

Profile text:
{{page_text}}
"""


def _scrape_text(linkedin_url: str) -> str:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30_000)
        if "/login" in page.url or "/checkpoint" in page.url:
            print("Operator: log in to LinkedIn in the opened window, then press Enter here.", flush=True)
            input()
        page.goto(linkedin_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(3_000)
        text = page.evaluate("() => document.body.innerText")
        context.close()
        return str(text)


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("https://"):
        print(__doc__, file=sys.stderr)
        return 2
    linkedin_url = sys.argv[1].rstrip("/")
    print(f"Scraping {linkedin_url} ...", flush=True)
    text = _scrape_text(linkedin_url)
    print(f"Got {len(text)} chars; extracting via LLM ...", flush=True)
    extracted = call_json(
        model="gemini-2.5-flash",
        system="You extract structured candidate data from LinkedIn profile text.",
        user=EXTRACT_PROMPT.replace("{{page_text}}", text[:25_000]),
        max_tokens=4000,
    )
    print("LLM result:")
    print(json.dumps(extracted, indent=2, ensure_ascii=False)[:800])
    payload = {
        "linkedin_url": linkedin_url,
        "full_name": extracted.get("full_name") or "",
        "headline": extracted.get("headline") or "",
        "location": extracted.get("location") or "",
        "summary": extracted.get("summary") or "",
        "skills": extracted.get("skills") or [],
        "positions": extracted.get("positions") or [],
        "education": extracted.get("education") or [],
        "languages": extracted.get("languages") or {},
        "linkedin_scraped_at": "now()",
    }
    if not payload["full_name"]:
        print("ERROR: LLM didn't extract a name — check page text", file=sys.stderr)
        return 1
    payload.pop("linkedin_scraped_at")  # let DB default
    upsert_profile(payload)
    print(f"Upserted profile for {payload['full_name']!r}.", flush=True)
    print(f"Set JOBSCOUT_PROFILE_LINKEDIN_URL={linkedin_url} in .env", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Operator runs it against their own LinkedIn as a smoke test**

```bash
poetry run python scripts/bootstrap_profile_from_linkedin.py https://www.linkedin.com/in/izabel-cvetkovic/
```

Expected: opens a Chromium window (first time: log in manually, press Enter in terminal; subsequent runs: session persists), navigates to your own LinkedIn profile, prints the extracted JSON, prints "Upserted profile for 'Izabel Cvetkovic'."

- [ ] **Step 3: Verify the DB row**

```bash
poetry run python -c "
from jobscout.db import get_profile
p = get_profile('https://www.linkedin.com/in/izabel-cvetkovic')
print(p.get('full_name'), '|', p.get('headline'))
print('skills:', p.get('skills')[:5])
print('positions:', len(p.get('positions') or []))
"
```

Expected: shows name, headline, top-5 skills, position count > 0.

- [ ] **Step 4: Commit**

```bash
git add scripts/bootstrap_profile_from_linkedin.py
git commit -m "feat(scripts): bootstrap_profile_from_linkedin — one-shot operator script"
```

---

## Task 16: Wire discover → filter → score → draft against new profile + new sources

**Files:**
- Modify: `jobscout/discover.py`
- Modify: `jobscout/filter.py` (the entrypoint module, distinct from `filters.py` which has the helpers)
- Modify: `jobscout/score.py`
- Modify: `jobscout/draft.py`
- Create: `tests/test_pipeline_smoke.py`

**Goal:** end-to-end smoke that discover → filter → score → draft writes rows to Supabase.

- [ ] **Step 1: Enumerate every YAML-flavoured profile access that needs renaming**

```bash
grep -n -E "(profile\[\"candidate_contact\"\]|profile\[\"candidate_languages\"\]|anchor_case_studies|sensitive_field_defaults|target_rate_floor_(usd|eur)_hr|max_hours_per_week|languages_accepted|required_skill_keywords|title_denylist|model_score|model_draft|prompt_versions|photo_path)" jobscout/ --include='*.py'
```

For each match, apply this rename map (sidegig YAML key → jobscout DB column or removal):

| sidegig (YAML) | jobscout (DB column) | notes |
|---|---|---|
| `profile["candidate_contact"]["email"]` | `profile["email"]` | flatten |
| `profile["candidate_contact"]["phone"]` | `profile["phone"]` | flatten |
| `profile["candidate_contact"]["location"]` | `profile["location"]` | flatten |
| `profile["candidate_contact"]["linkedin"]` | `profile["linkedin_url"]` | flatten + rename |
| `profile["candidate_contact"]["years_experience"]` | `profile["years_experience"]` | already top-level in schema |
| `profile["candidate_contact"]["work_authorization"]` | *drop* | not in Phase 2 schema |
| `profile["candidate_contact"]["portfolio"]` | *drop* | not in Phase 2 schema |
| `profile["candidate_languages"]` | `profile["languages"]` | shape unchanged (dict[str,str]) |
| `profile["sensitive_field_defaults"]` | *drop* | apply-time concern, defer to Phase 4 |
| `profile["target_rate_floor_eur_hr"]` | `profile["target_rate_floor_eur"]` | rename, drop `_hr` |
| `profile["target_rate_floor_usd_hr"]` | *drop* | EU-only scope |
| `profile["max_hours_per_week"]` | *drop* | full-time scope, no hour cap |
| `profile["languages_accepted"]` | *hardcode* `["de", "en"]` | static for this user |
| `profile["required_skill_keywords"]` | `profile["required_skill_keywords"]` | unchanged |
| `profile["title_denylist"]` | `profile["title_denylist"]` | unchanged |
| `profile["embedding_threshold"]` | *hardcode* `0.30` | constant |
| `profile["anchor_case_studies"]` | `profile["anchor_summaries"]` | rename; shape unchanged (list[{title, summary}]) |
| `profile["model_score"]`, `profile["model_draft"]` | *hardcode* `"gemini-2.5-flash"` | spec decision |
| `profile["prompt_versions"]` | *hardcode* `{"score": "v1", "draft_proposal": "v1", "draft_cv": "v1"}` | constant |
| `profile["photo_path"]` | *drop* | not in CV render scope yet |
| `profile["linkedin_company_denylist"]` | *defer to Phase 4* | re-introduce when apply lands |
| `profile["apply_daily_caps"]` | *hardcode* `10` total | spec decision |

Apply each rename in the matching file. Where a value is hardcoded above, define it as a module-level constant in the file that uses it (e.g. `_LANGUAGES_ACCEPTED = ("de", "en")` near the top of `filters.py`).

For `embeddings.py` specifically: it likely reads `profile["anchor_case_studies"]` to build the comparison embedding. Update to `profile["anchor_summaries"]` and verify the shape (list of `{"title": str, "summary": str}` objects).

- [ ] **Step 2: Update `draft.py` to use new profile fields**

Where sidegig's `draft.py` references e.g. `profile["candidate_contact"]["email"]` (which came from YAML), replace with the DB equivalents. The new profile shape (per Task 13 schema) has:
- `full_name`, `email`, `phone`, `location`, `headline`, `summary`, `skills`, `positions`
- `required_skill_keywords`, `title_denylist`, `arrangement_preferences`, `anchor_summaries`
- `cv_markdown`

Walk through `draft.py` line-by-line. Replace any `profile["sub"]["key"]` with `profile.get("sub_key")` matching the flatter DB schema.

For the prompt template substitution dict (sidegig has `_candidate_context()`), build the same shape:

```python
def _candidate_context(profile: dict[str, Any]) -> dict[str, str]:
    languages = profile.get("languages") or {}
    lang_lines = "\n".join(f"  - {k}: {v}" for k, v in languages.items()) or "  (none configured)"
    return {
        "candidate_name": profile.get("full_name", ""),
        "candidate_email": profile.get("email", ""),
        "candidate_phone": profile.get("phone", ""),
        "candidate_location": profile.get("location", ""),
        "candidate_linkedin": profile.get("linkedin_url", ""),
        "candidate_headline": profile.get("headline", ""),
        "candidate_summary": profile.get("summary", ""),
        "candidate_skills": ", ".join(profile.get("skills") or []),
        "candidate_languages": lang_lines,
    }
```

Remove references to `candidate_contact.work_authorization`, `years_experience`, `target_rate_floor_*` since those aren't in the new schema yet (or update the schema in Task 13 to add them — your call; for MVP, omit).

- [ ] **Step 3: Write the end-to-end smoke test**

`tests/test_pipeline_smoke.py`:

```python
"""End-to-end smoke against fixtures + a stubbed LLM. Runs discovery on
fixture data (no live LinkedIn / Indeed), filters with the inverted rule
set, exercises the score+draft path with the LLM stubbed.

Asserts: rows land in Supabase, filtered rows match expectations, scored
rows have rationale, drafts have body.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

FIXTURES_LI = Path(__file__).parent / "fixtures" / "listings" / "linkedin"
FIXTURES_IND = Path(__file__).parent / "fixtures" / "listings" / "indeed"
TEST_URL = "https://www.linkedin.com/in/__jobscout_test_user_pipeline__/"


def _df(d: Path) -> pd.DataFrame:
    return pd.DataFrame(
        [json.loads(f.read_text()) for f in sorted(d.glob("*.json")) if not f.name.endswith(".labels.json")]
    )


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setenv("JOBSCOUT_PROFILE_LINKEDIN_URL", TEST_URL)
    from jobscout.config_loader import clear_profile_cache
    from jobscout.db import _client, upsert_profile

    upsert_profile(
        {
            "full_name": "Test User",
            "linkedin_url": TEST_URL,
            "headline": "ML Engineer",
            "skills": ["Python", "PyTorch", "LLM", "RAG"],
            "required_skill_keywords": ["LLM"],
            "title_denylist": ["WordPress"],
            "arrangement_preferences": ["remote", "hybrid"],
        }
    )
    clear_profile_cache()
    yield
    _client().table("profiles").delete().eq("linkedin_url", TEST_URL).execute()


@pytest.mark.skipif(not os.environ.get("SUPABASE_URL"), reason="needs supabase")
def test_pipeline_end_to_end(monkeypatch):
    # Stub scrape
    from jobscout.sources import indeed as ind_mod
    from jobscout.sources import linkedin as li_mod

    monkeypatch.setattr(li_mod, "_scrape", lambda **_: _df(FIXTURES_LI))
    monkeypatch.setattr(ind_mod, "_scrape", lambda **_: _df(FIXTURES_IND))

    # Stub LLM
    from jobscout import llm as llm_mod

    def fake_call_json(model: str, system: str, user: str, max_tokens: int) -> dict[str, Any]:
        if "score" in (user or "").lower()[:200]:
            return {"score": 75, "rationale": "fixture score"}
        return {"subject": "Application", "body": "fixture draft body", "adapted_cv": "# CV"}

    monkeypatch.setattr(llm_mod, "call_json", fake_call_json)

    # Run discover (writes to Supabase)
    from jobscout import discover as disc_mod

    n = disc_mod.run_all()  # operator may need to add this entrypoint if not present
    assert n >= 1
```

Note: if `discover.run_all()` doesn't exist in your current `discover.py`, add it as a thin wrapper that iterates `_SOURCES` and persists.

- [ ] **Step 4: Run, observe, iterate**

```bash
poetry run pytest tests/test_pipeline_smoke.py -v
```

Expected first run: probably fails on something — `draft.py` referencing a missing profile field, or `score.py` similar. Read trace, fix, re-run. Iterate until green.

- [ ] **Step 5: Manual end-to-end verification**

Set `JOBSCOUT_PROFILE_LINKEDIN_URL` to your own LinkedIn (the one populated in Task 15), then:

```bash
poetry run python -m jobscout.discover --only linkedin --limit 5
poetry run python -m jobscout.filter
poetry run python -m jobscout.score
```

Expected: progresses through stages without unhandled exceptions, persists rows visible in the Supabase web UI.

- [ ] **Step 6: Commit**

```bash
git add jobscout/discover.py jobscout/filter.py jobscout/score.py jobscout/draft.py tests/test_pipeline_smoke.py
git commit -m "feat(pipeline): wire discover→filter→score→draft against DB-backed profile"
```

---

## Task 17: README + Makefile finalisation, lint + type clean

**Files:**
- Modify: `README.md`
- Modify: `Makefile`

- [ ] **Step 1: Update README with current setup steps**

Replace `README.md` with:

```markdown
# jobscout

Hamburg-region full-time job discovery + AI drafting for a non-technical end user.
Forked from `sidegig` with these material differences:
- Sources: LinkedIn + Indeed only
- Roles: full-time / permanent only
- Geography: Hamburg only
- Apply: external-ATS only (Phase 4, separate plan)
- Profile: stored in DB, not YAML

See `docs/superpowers/specs/2026-05-20-jobscout-design.md` for the design.

## Setup (operator, one-time per new end-user)

1. `cp .env.example .env` and fill in:
   - `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (new jobscout project)
   - `GEMINI_API_KEY` (re-use from sidegig)
   - `JOBSCOUT_PROFILE_LINKEDIN_URL` = end-user's LinkedIn URL
2. `make install`
3. `supabase link --project-ref <ref>` then `supabase db push` to apply migrations
4. `poetry run python scripts/bootstrap_profile_from_linkedin.py <user_linkedin_url>`

## Daily run (Phase 0–2 scope — manual)

```bash
make discover    # scrape LinkedIn + Indeed, persist to Supabase
make filter      # apply hard filters
make score       # LLM-score survivors
```

(Phases 3–6 add Streamlit UI, apply pipeline, Windows installer — separate plans.)

## Phase 0 — fixture / classifier maintenance

Refresh the fixture corpus + relabel when classifier drift is suspected:

```bash
poetry run python scripts/capture_fixtures.py
poetry run python scripts/label_fixtures.py
# (operator manually verifies labels)
poetry run pytest tests/test_derive_*.py -v
```
```

- [ ] **Step 2: Update Makefile targets**

Edit `Makefile` so the targets match the new package name and the Phase 0–2 scope. Verify by running:

```bash
make install
make lint
make type
make test
```

Expected: each runs without unhandled errors. Lint/type warnings → fix per the user's global "zero warnings" policy.

- [ ] **Step 3: Commit**

```bash
git add README.md Makefile
git commit -m "docs: finalize README + Makefile for Phase 0–2 scope"
```

---

## Self-review checklist (do this before declaring the plan done)

After implementing through Task 17, the operator should run this final pass:

- [ ] `poetry run pytest -q` — all tests pass, including the fixture-driven classifier tests at ≥95% accuracy
- [ ] `poetry run ruff check .` — clean
- [ ] `poetry run ruff format --check .` — clean
- [ ] `poetry run mypy jobscout` — clean
- [ ] A manual `make discover && make filter && make score` produces fresh rows in Supabase
- [ ] Spot-check 5 random listings in Supabase: do `arrangement`, `job_type_classified`, `apply_method` look right?
- [ ] The `profiles` row for the end user (or your test profile) has skills + positions + headline populated
- [ ] No lingering references to `upwork`, `bundesagentur`, `freelancermap`, `onboarding`, `weasyprint`, `pyperclip` in code:
  ```bash
  grep -rn -E "(upwork|bundesagentur|freelancermap|onboarding|weasyprint|pyperclip)" jobscout tests scripts --include='*.py' | grep -v "no remote" | head
  ```
  Expected: empty.

When all 8 boxes tick, Phase 0–2 is complete. Hand off to the brainstorming → writing-plans pipeline for Phase 3 (Streamlit UI + shadcn-ui upgrade).

---

## Out of scope for this plan

The following are deferred to follow-up plans, each of which will reference the same design spec:

- **CV bootstrap** (`scripts/bootstrap_profile_from_cv.py`) — the operator doesn't have the end-user's CV yet (the user said "later I will give you more details when I have them (in form of CV)"). Adding it now would be writing code we can't run. Defer to the moment the CV arrives; it's a ~30-line script that merges PDF-extracted CV data into the existing `profiles` row by `linkedin_url`. Slot into either the tail of Phase 2 (when CV arrives) or Phase 3 plan.
- **Phase 3: Streamlit UI** — card layout via `streamlit-shadcn-ui`, KPI hero, Settings tab editor for the `profiles` row, hidden `/admin` route. (Plan 2)
- **Phase 4: Apply pipeline** — `apply_requests` table migration, port of `external_ats.py` + worker, 10/day cap, `page.pdf()` CV render replacing WeasyPrint, macOS launchd plist for dev. (Plan 3)
- **Phase 5: Windows installer** — Briefcase MSI, `chrome-cdp.bat`, Task Scheduler XML, post-install + pre-uninstall scripts, Edge fallback. (Plan 4)
- **Phase 6: Operator handover** — install on user's Windows laptop, walkthrough. (Plan 5 — or maybe a checklist rather than a code plan.)

Each follow-up plan should be written after the prior plan's outputs reveal what's actually needed (e.g. how the DB row shape evolved during Phase 2 affects what the Settings tab edits in Phase 3).

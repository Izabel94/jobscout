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
    "Backend Engineer",
    "Data Engineer",
    "MLOps Engineer",
    "LLM Engineer",
    "Full Stack Engineer",
    "DevOps Engineer",
    "Cloud Engineer",
    "Frontend Engineer",
    "NLP Engineer",
    "Computer Vision Engineer",
    "Senior Software Engineer",
    "Java Developer",
    "Site Reliability Engineer",
    "Platform Engineer",
    "Research Engineer",
]


def _safe(d: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        if v is None or isinstance(v, str | int | float | bool | list | dict):
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

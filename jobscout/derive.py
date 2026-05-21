"""Per-source field classifiers — arrangement, job_type, apply_method.

Patterns live here (production source of truth) and are imported by
scripts/label_fixtures.py for fixture pre-labelling. Both sides MUST stay
in sync — the fixture test in tests/test_derive_arrangement.py catches
drift.

Vocabulary observed in fixture corpus (96 LinkedIn + 37 Indeed from
Hamburg, 2026-05-20 capture):
- `is_remote`: bool, JobSpy heuristic. Common but treats hybrid as either
  True or False inconsistently. Useful only as a fallback signal.
- `work_from_home_type`: str | None, Indeed-only. Null in 100% of current
  corpus but reliable when populated ("Hybrid", "Remote",
  "Temporarily remote").
- `job_type`: str | list[str] | None. JobSpy's parsed field; often "fulltime",
  occasionally "parttime, fulltime", sometimes NaN for Indeed.
- `company_url_direct`: str | None. The off-platform apply URL. Null in
  100% of LinkedIn corpus, populated in 97% of Indeed corpus.
"""

from __future__ import annotations

import math
import re
from typing import Any

from jobscout.models import ApplyMethod, Arrangement, JobType

ONSITE_PATTERNS = [
    r"\b5\s*(?:days?|tage)\s*(?:/|per\s+|im\s+|in\s+)?\s*(?:week|wk|woche)",
    r"\bfull\s*[-\s]?(?:time|day)\s+(?:on[-\s]?site|in[-\s]?office)",
    r"\bvollständig\s+vor\s+ort\b",
    r"\b100\s*%\s*(?:on[-\s]?site|vor\s+ort)",
    r"\bno\s+(?:remote|home\s+office)\b",
    r"\bnicht\s+(?:remote|home\s+office)\b",
]

HYBRID_PATTERNS = [
    r"\bhybrid\b",
    r"\b(?:few|some|2|3|4)\s*(?:days?|tage)\s*(?:/|per\s+|im\s+|in\s+)?\s*(?:week|wk|woche|office|büro)",
    r"\b(?:days?|tage)\s+in\s+(?:the\s+)?(?:office|büro)",
    r"\bteilweise\s+vor\s+ort\b",
    r"\b\d+\s*(?:days?|tage)\s+(?:per|pro)?\s*(?:week|woche)?\s*(?:office|büro|on[-\s]?site|vor\s+ort)",
]

REMOTE_PATTERNS = [
    r"\b(?:fully|100\s*%)?\s*remote\b",
    r"\bhome\s*[-\s]?office\b",
    r"\bwork[-\s]?from[-\s]?home\b",
    r"\bortsunabhängig\b",
    r"\bmostly\s+(?:directly\s+)?at\s+your\s+home",
]

INTERN_PATTERNS = [
    r"\b(?:intern(?:ship)?|praktikum|werkstudent)\b",
]

PARTTIME_PATTERNS = [
    r"\b(?:part[-\s]?time|teilzeit)\b",
    r"\b(?:20|24|25|30)\s*(?:h|hours?|stunden?)\s*/?\s*(?:per\s+|pro\s+)?(?:week|woche)\b",
]

CONTRACT_PATTERNS = [
    r"\b(?:contract|contractor|freelance|freiberuflich)\b",
    r"\bbefristet\b",
    r"\bfixed[-\s]?term\b",
]

PERMANENT_PATTERNS = [
    r"\b(?:permanent|unbefristet|festanstellung)\b",
]

FULLTIME_PATTERNS = [
    r"\b(?:full[-\s]?time|fulltime|vollzeit)\b",
    r"\b40\s*(?:h|hours?|stunden?)\s*/?\s*(?:per\s+|pro\s+)?(?:week|woche)\b",
]


def _str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    return str(v)


def haystack(raw: dict[str, Any]) -> str:
    return " ".join(_str(raw.get(k)) for k in ("title", "description", "location", "work_from_home_type")).lower()


def first_match(patterns: list[str], text: str) -> str:
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(0)
    return ""


def classify_arrangement(raw: dict[str, Any]) -> tuple[Arrangement, str]:
    wfh = _str(raw.get("work_from_home_type")).strip().lower()
    if wfh == "hybrid":
        return Arrangement.HYBRID, "indeed.work_from_home_type=Hybrid"
    if wfh in ("remote", "temporarily remote"):
        return Arrangement.REMOTE, f"indeed.work_from_home_type={raw['work_from_home_type']}"
    text = haystack(raw)
    if hit := first_match(ONSITE_PATTERNS, text):
        return Arrangement.ONSITE, hit
    if hit := first_match(HYBRID_PATTERNS, text):
        return Arrangement.HYBRID, hit
    if hit := first_match(REMOTE_PATTERNS, text):
        return Arrangement.REMOTE, hit
    if raw.get("is_remote") is True:
        return Arrangement.REMOTE, "jobspy.is_remote=True"
    return Arrangement.UNKNOWN, ""


def normalize_jobspy_job_type(raw: dict[str, Any]) -> str:
    """JobSpy may surface job_type as str, list[str], None, or NaN-float."""
    jt = raw.get("job_type")
    if isinstance(jt, list):
        return " ".join(_str(x) for x in jt).lower()
    return _str(jt).lower()


def classify_job_type(raw: dict[str, Any]) -> tuple[JobType, str]:
    jt = normalize_jobspy_job_type(raw)
    if "intern" in jt:
        return JobType.INTERN, f"jobspy.job_type={raw.get('job_type')!r}"
    if "part" in jt and "full" not in jt:
        return JobType.PARTTIME, f"jobspy.job_type={raw.get('job_type')!r}"
    if "contract" in jt or "temporary" in jt:
        return JobType.CONTRACT, f"jobspy.job_type={raw.get('job_type')!r}"
    if "permanent" in jt:
        return JobType.PERMANENT, f"jobspy.job_type={raw.get('job_type')!r}"
    if "full" in jt or "fulltime" in jt:
        return JobType.FULLTIME, f"jobspy.job_type={raw.get('job_type')!r}"

    text = haystack(raw)
    if hit := first_match(INTERN_PATTERNS, text):
        return JobType.INTERN, hit
    if hit := first_match(PARTTIME_PATTERNS, text):
        return JobType.PARTTIME, hit
    if hit := first_match(CONTRACT_PATTERNS, text):
        return JobType.CONTRACT, hit
    if hit := first_match(PERMANENT_PATTERNS, text):
        return JobType.PERMANENT, hit
    if hit := first_match(FULLTIME_PATTERNS, text):
        return JobType.FULLTIME, hit
    return JobType.UNKNOWN, ""


def classify_apply_method(raw: dict[str, Any]) -> tuple[ApplyMethod, str]:
    raise NotImplementedError  # Task 7

"""Generate ground-truth labels for each captured fixture using regex
heuristics over title + description. No paid LLM calls.

Sidegig uses regex-based classification for similar workloads (rate
parsing, job-type detection, etc.); same approach here. Operator
hand-verifies labels where confidence is low.

LinkedIn apply_method is hardcoded to easy_apply (company_url_direct is
empty in 100% of the corpus — see project memory
jobspy-linkedin-company-url-direct-empty). Indeed apply_method comes from
company_url_direct presence.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DIRS = [
    (ROOT / "tests" / "fixtures" / "listings" / "linkedin", "linkedin"),
    (ROOT / "tests" / "fixtures" / "listings" / "indeed", "indeed"),
]

# Arrangement patterns. Order matters: onsite (most specific) first, then
# hybrid, then remote. Each list is checked against title + description +
# location lowercased.

_ONSITE_PATTERNS = [
    r"\b5\s*(?:days?|tage)\s*(?:/|per\s+|im\s+|in\s+)?\s*(?:week|wk|woche)",
    r"\bfull\s*[-\s]?(?:time|day)\s+(?:on[-\s]?site|in[-\s]?office)",
    r"\bvollständig\s+vor\s+ort\b",
    r"\b100\s*%\s*(?:on[-\s]?site|vor\s+ort)",
    r"\bno\s+(?:remote|home\s+office)\b",
    r"\bnicht\s+(?:remote|home\s+office)\b",
]

_HYBRID_PATTERNS = [
    r"\bhybrid\b",
    r"\b(?:few|some|2|3|4)\s*(?:days?|tage)\s*(?:/|per\s+|im\s+|in\s+)?\s*(?:week|wk|woche|office|büro)",
    r"\b(?:days?|tage)\s+in\s+(?:the\s+)?(?:office|büro)",
    r"\bteilweise\s+vor\s+ort\b",
    r"\b\d+\s*(?:days?|tage)\s+(?:per|pro)?\s*(?:week|woche)?\s*(?:office|büro|on[-\s]?site|vor\s+ort)",
]

_REMOTE_PATTERNS = [
    r"\b(?:fully|100\s*%)?\s*remote\b",
    r"\bhome\s*[-\s]?office\b",
    r"\bwork[-\s]?from[-\s]?home\b",
    r"\bortsunabhängig\b",
    r"\bmostly\s+(?:directly\s+)?at\s+your\s+home",
]

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


def _haystack(raw: dict[str, Any]) -> str:
    parts = [
        str(raw.get("title") or ""),
        str(raw.get("description") or ""),
        str(raw.get("location") or ""),
        str(raw.get("work_from_home_type") or ""),
    ]
    return " ".join(parts).lower()


def _first_match(patterns: list[str], text: str) -> str:
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(0)
    return ""


def _suggest_arrangement(raw: dict[str, Any]) -> tuple[str, str]:
    wfh = (raw.get("work_from_home_type") or "").strip().lower()
    if wfh == "hybrid":
        return "hybrid", "indeed.work_from_home_type=Hybrid"
    if wfh in ("remote", "temporarily remote"):
        return "remote", f"indeed.work_from_home_type={raw['work_from_home_type']}"
    text = _haystack(raw)
    if hit := _first_match(_ONSITE_PATTERNS, text):
        return "onsite", hit
    if hit := _first_match(_HYBRID_PATTERNS, text):
        return "hybrid", hit
    if hit := _first_match(_REMOTE_PATTERNS, text):
        return "remote", hit
    if raw.get("is_remote") is True:
        return "remote", "jobspy.is_remote=True"
    return "unknown", ""


def _normalize_jobspy_jt(raw: dict[str, Any]) -> str:
    jt = raw.get("job_type")
    if isinstance(jt, list):
        return " ".join(str(x) for x in jt).lower()
    if isinstance(jt, str):
        return jt.lower()
    return ""  # None, NaN, etc.


def _suggest_job_type(raw: dict[str, Any]) -> tuple[str, str]:
    jt = _normalize_jobspy_jt(raw)
    if "intern" in jt:
        return "intern", f"jobspy.job_type={raw.get('job_type')!r}"
    if "part" in jt and "full" not in jt:
        return "parttime", f"jobspy.job_type={raw.get('job_type')!r}"
    if "contract" in jt or "temporary" in jt:
        return "contract", f"jobspy.job_type={raw.get('job_type')!r}"
    if "permanent" in jt:
        return "permanent", f"jobspy.job_type={raw.get('job_type')!r}"
    if "full" in jt or "fulltime" in jt:
        return "fulltime", f"jobspy.job_type={raw.get('job_type')!r}"

    text = _haystack(raw)
    if hit := _first_match(_INTERN_PATTERNS, text):
        return "intern", hit
    if hit := _first_match(_PARTTIME_PATTERNS, text):
        return "parttime", hit
    if hit := _first_match(_CONTRACT_PATTERNS, text):
        return "contract", hit
    if hit := _first_match(_PERMANENT_PATTERNS, text):
        return "permanent", hit
    if hit := _first_match(_FULLTIME_PATTERNS, text):
        return "fulltime", hit
    return "unknown", ""


def _apply_method_for(source: str, raw: dict[str, Any]) -> str:
    if source == "linkedin":
        return "easy_apply"
    # Indeed's company_url_direct comes from JobSpy as either a string, None,
    # or float NaN (pandas leakage). Treat any non-string as "no URL".
    raw_url = raw.get("company_url_direct")
    url = raw_url.strip() if isinstance(raw_url, str) else ""
    return "external_apply" if url else "easy_apply"


def main() -> int:
    n = 0
    for d, source in DIRS:
        if not d.exists():
            continue
        for fp in sorted(d.glob("*.json")):
            if fp.name.endswith(".labels.json"):
                continue
            labels_fp = fp.with_suffix(".labels.json")
            if labels_fp.exists():
                continue

            raw = json.loads(fp.read_text())
            arr, arr_ev = _suggest_arrangement(raw)
            jt, jt_ev = _suggest_job_type(raw)
            labels_fp.write_text(
                json.dumps(
                    {
                        "expected_arrangement": arr,
                        "arrangement_evidence": arr_ev,
                        "expected_job_type": jt,
                        "job_type_evidence": jt_ev,
                        "expected_apply_method": _apply_method_for(source, raw),
                        "labeler": "regex-heuristic",
                        "verified_by_operator": False,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            n += 1
    print(f"Labels written: {n}")
    print("Operator: spot-check a sample; flip verified_by_operator=true once satisfied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

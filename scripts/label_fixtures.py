"""Generate ground-truth labels for each captured fixture, using Gemini
Flash Lite as an oracle. Each fixture gets a sibling .labels.json with
expected_arrangement, expected_job_type, expected_apply_method.

LinkedIn apply_method is hardcoded to easy_apply (company_url_direct is
empty in 100% of the corpus — see project memory
jobspy-linkedin-company-url-direct-empty). Indeed apply_method is set from
company_url_direct presence.

The other two fields (arrangement, job_type) are LLM-classified from
title + description text. Operator spot-checks a random sample after the
script runs.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from jobscout.llm import LLMJSONError, call_json, call_text

load_dotenv()

# Matches a trailing comma before } or ]. gemini-2.5-flash-lite emits these
# on long reasoning strings; strict json.loads rejects them.
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")

# Daily-quota 429s mean the operator must wait for reset (≈ midnight Pacific) or
# upgrade the plan — no point retrying the rest of the corpus in this run.
_DAILY_QUOTA_MARKER = "PerDay"

ROOT = Path(__file__).resolve().parent.parent
DIRS = [
    (ROOT / "tests" / "fixtures" / "listings" / "linkedin", "linkedin"),
    (ROOT / "tests" / "fixtures" / "listings" / "indeed", "indeed"),
]

ARRANGEMENT_VALUES = ["remote", "hybrid", "onsite", "unknown"]
JOB_TYPE_VALUES = ["fulltime", "permanent", "contract", "parttime", "intern", "unknown"]

PROMPT = """You label one job listing for two enums.

Listing:
  Title: {{title}}
  Location: {{location}}
  is_remote: {{is_remote}}
  job_type: {{job_type}}
  work_from_home_type: {{work_from_home_type}}
  Description:
{{description}}

Return JSON exactly matching this schema (no markdown fences):
{
  "expected_arrangement": one of [remote, hybrid, onsite, unknown],
  "expected_job_type": one of [fulltime, permanent, contract, parttime, intern, unknown],
  "arrangement_reasoning": "1-sentence why",
  "job_type_reasoning": "1-sentence why"
}

Rules:
- "remote" = 100% remote / home office / no on-site requirement.
- "hybrid" = some days in office (e.g. "2-3 days/week in office").
- "onsite" = full on-site, no remote work mentioned (e.g. "5 days/week in office", "fully on-site", "vor Ort").
- "unknown" = not stated either way.
- "permanent" wins over "fulltime" when both apply (e.g. "permanent / unbefristet" → permanent).
- "intern" includes Praktikum / Werkstudent.
- If multiple types apply (e.g. JobSpy returned "parttime, fulltime"), prefer the more committed type (fulltime > parttime).
"""


def _apply_method_for(source: str, raw: dict[str, Any]) -> str:
    if source == "linkedin":
        return "easy_apply"
    url = (raw.get("company_url_direct") or "").strip()
    return "external_apply" if url else "easy_apply"


def _salvage_json(raw_text: str) -> dict[str, Any]:
    """gemini-2.5-flash-lite sometimes emits trailing commas. Strip them and
    re-parse. Also tolerate ```json fenced output."""
    s = raw_text.strip()
    if s.startswith("```"):
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
    s = _TRAILING_COMMA_RE.sub(r"\1", s.strip())
    parsed = json.loads(s)
    if not isinstance(parsed, dict):
        raise LLMJSONError(f"expected dict, got {type(parsed).__name__}")
    return parsed


def _label_with_llm(raw: dict[str, Any]) -> dict[str, Any]:
    desc = str(raw.get("description") or "")[:6000]
    user = (
        PROMPT.replace("{{title}}", str(raw.get("title") or ""))
        .replace("{{location}}", str(raw.get("location") or ""))
        .replace("{{is_remote}}", str(raw.get("is_remote")))
        .replace("{{job_type}}", str(raw.get("job_type")))
        .replace("{{work_from_home_type}}", str(raw.get("work_from_home_type")))
        .replace("{{description}}", desc)
    )
    model = "gemini-2.5-flash-lite"
    system = "You classify job listings into structured enums. Be conservative; prefer 'unknown' when unsure."
    try:
        result = call_json(model=model, system=system, user=user, max_tokens=600)
    except LLMJSONError:
        # Re-call as plain text and salvage trailing-comma JSON locally.
        raw_text = call_text(model=model, system=system, user=user, max_tokens=600)
        result = _salvage_json(raw_text)
    arr = (result.get("expected_arrangement") or "").strip().lower()
    jt = (result.get("expected_job_type") or "").strip().lower()
    if arr not in ARRANGEMENT_VALUES:
        arr = "unknown"
    if jt not in JOB_TYPE_VALUES:
        jt = "unknown"
    return {
        "expected_arrangement": arr,
        "expected_job_type": jt,
        "arrangement_reasoning": result.get("arrangement_reasoning") or "",
        "job_type_reasoning": result.get("job_type_reasoning") or "",
    }


def main() -> int:
    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY not in env", file=sys.stderr)
        return 1

    new_labels = 0
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
            try:
                labelled = _label_with_llm(raw)
            except Exception as e:
                msg = repr(e)
                print(f"  {fp.name}: LLM error {msg} — skipping", file=sys.stderr)
                if _DAILY_QUOTA_MARKER in msg:
                    print(
                        "Daily Gemini free-tier quota exhausted. Re-run after reset.",
                        file=sys.stderr,
                    )
                    print(f"Total labels written: {new_labels}")
                    return 0
                continue

            labelled["expected_apply_method"] = _apply_method_for(source, raw)
            labelled["verified_by_operator"] = False
            labelled["labeler"] = "gemini-2.5-flash-lite"
            labels_fp.write_text(json.dumps(labelled, indent=2, ensure_ascii=False))
            new_labels += 1
            if new_labels % 10 == 0:
                print(f"  …labelled {new_labels} so far", flush=True)
                time.sleep(0.2)

    print(f"Total labels written: {new_labels}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

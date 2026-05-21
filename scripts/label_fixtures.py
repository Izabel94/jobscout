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
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jobscout.derive import (  # noqa: E402
    classify_apply_method,
    classify_arrangement,
    classify_job_type,
)

DIRS = [
    (ROOT / "tests" / "fixtures" / "listings" / "linkedin", "linkedin"),
    (ROOT / "tests" / "fixtures" / "listings" / "indeed", "indeed"),
]


def _suggest_arrangement(raw: dict[str, Any]) -> tuple[str, str]:
    arr, ev = classify_arrangement(raw)
    return arr.value, ev


def _suggest_job_type(raw: dict[str, Any]) -> tuple[str, str]:
    jt, ev = classify_job_type(raw)
    return jt.value, ev


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
            am, _am_ev = classify_apply_method(source, raw)
            labels_fp.write_text(
                json.dumps(
                    {
                        "expected_arrangement": arr,
                        "arrangement_evidence": arr_ev,
                        "expected_job_type": jt,
                        "job_type_evidence": jt_ev,
                        "expected_apply_method": am.value,
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

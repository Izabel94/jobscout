"""Validates classify_job_type against the hand-labelled fixture corpus.

Acknowledged circularity: labeller (scripts/label_fixtures.py) and
classifier (jobscout/derive.py) share regex patterns. This test guards
against pattern drift rather than measuring classifier correctness —
that's the operator's spot-check responsibility.
"""

from __future__ import annotations

import json
from pathlib import Path

from jobscout.derive import classify_job_type

FIXTURE_DIRS = [
    Path(__file__).parent / "fixtures" / "listings" / "linkedin",
    Path(__file__).parent / "fixtures" / "listings" / "indeed",
]


def _pairs():
    for d in FIXTURE_DIRS:
        for raw_fp in sorted(d.glob("*.json")):
            if raw_fp.name.endswith(".labels.json"):
                continue
            labels_fp = raw_fp.with_suffix(".labels.json")
            if not labels_fp.exists():
                continue
            yield raw_fp.name, json.loads(raw_fp.read_text()), json.loads(labels_fp.read_text())


def test_classifier_job_type_against_fixtures():
    pairs = list(_pairs())
    assert len(pairs) >= 60
    correct = 0
    mismatches: list[str] = []
    for name, raw, labels in pairs:
        expected = labels["expected_job_type"]
        actual_value, _ev = classify_job_type(raw)
        if actual_value.value == expected:
            correct += 1
        else:
            mismatches.append(f"  {name}: expected {expected!r}, got {actual_value.value!r}")
    accuracy = correct / len(pairs)
    msg = f"\nJob-type classifier accuracy: {accuracy:.1%} ({correct}/{len(pairs)})"
    if mismatches:
        msg += "\nMismatches:\n" + "\n".join(mismatches[:20])
    assert accuracy >= 0.95, msg

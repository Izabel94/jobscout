from __future__ import annotations

import json
from pathlib import Path

from jobscout.derive import classify_apply_method
from jobscout.models import ApplyMethod

FIXTURE_DIRS = [
    (Path(__file__).parent / "fixtures" / "listings" / "linkedin", "linkedin"),
    (Path(__file__).parent / "fixtures" / "listings" / "indeed", "indeed"),
]


def _pairs():
    for d, source in FIXTURE_DIRS:
        for raw_fp in sorted(d.glob("*.json")):
            if raw_fp.name.endswith(".labels.json"):
                continue
            labels_fp = raw_fp.with_suffix(".labels.json")
            if not labels_fp.exists():
                continue
            yield raw_fp.name, source, json.loads(raw_fp.read_text()), json.loads(labels_fp.read_text())


def test_classifier_apply_method_against_fixtures():
    pairs = list(_pairs())
    assert len(pairs) >= 60
    correct = 0
    mismatches: list[str] = []
    for name, source, raw, labels in pairs:
        expected = labels["expected_apply_method"]
        actual_value, _ev = classify_apply_method(source, raw)
        if actual_value.value == expected:
            correct += 1
        else:
            mismatches.append(f"  [{source}] {name}: expected {expected!r}, got {actual_value.value!r}")
    accuracy = correct / len(pairs)
    msg = f"\nApply-method classifier accuracy: {accuracy:.1%} ({correct}/{len(pairs)})"
    if mismatches:
        msg += "\nMismatches:\n" + "\n".join(mismatches[:20])
    assert accuracy >= 0.95, msg


def test_linkedin_always_easy_apply():
    """Empirical finding: company_url_direct is null in 100% of LinkedIn
    corpus from logged-out residential scraping. LinkedIn → easy_apply
    unconditionally."""
    actual, _ = classify_apply_method("linkedin", {"company_url_direct": "https://greenhouse.io/foo"})
    assert actual == ApplyMethod.EASY_APPLY
    actual, _ = classify_apply_method("linkedin", {})
    assert actual == ApplyMethod.EASY_APPLY


def test_indeed_uses_company_url_direct():
    actual, ev = classify_apply_method("indeed", {"company_url_direct": "https://boards.greenhouse.io/foo/jobs/123"})
    assert actual == ApplyMethod.EXTERNAL_APPLY
    assert "greenhouse" in ev

    actual, ev = classify_apply_method("indeed", {"company_url_direct": None})
    assert actual == ApplyMethod.EASY_APPLY

    actual, ev = classify_apply_method("indeed", {"company_url_direct": ""})
    assert actual == ApplyMethod.EASY_APPLY

    actual, ev = classify_apply_method("indeed", {})
    assert actual == ApplyMethod.EASY_APPLY

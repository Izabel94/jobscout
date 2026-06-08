from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from jobscout.models import ApplyMethod, Arrangement, JobType, RateUnit, Source
from jobscout.sources.linkedin import LinkedInSource, _parse_rate_from_description

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "listings" / "linkedin"


def _load_fixtures_as_df() -> pd.DataFrame:
    rows = []
    for fp in sorted(FIXTURE_DIR.glob("*.json")):
        if fp.name.endswith(".labels.json"):
            continue
        rows.append(json.loads(fp.read_text()))
    return pd.DataFrame(rows)


def test_listing_normalization(monkeypatch):
    fake_df = pd.DataFrame(
        [
            {
                "id": "x123",
                "site": "linkedin",
                "job_url": "https://linkedin.com/jobs/view/x123",
                "title": "AI Engineer Freelance Remote",
                "description": "We use LangChain and Anthropic Claude. Hourly contract, 10h/week.",
                "company": "ACME GmbH",
                "location": "Berlin, Germany",
                "job_type": "contract",
                "is_remote": True,
            }
        ]
    )
    monkeypatch.setattr("jobscout.sources.linkedin._scrape", lambda **kw: fake_df)
    out = LinkedInSource(search_terms=["AI engineer"]).discover()
    assert len(out) == 1
    assert out[0].source == Source.LINKEDIN
    assert out[0].remote is True


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # En-dash range (the form Alignerr-style listings use). The literal
        # en-dash is intentional — that's what real listings emit.
        ("Compensation: $35–$60 /hour", (Decimal(35), Decimal(60), RateUnit.HOUR, "USD")),  # noqa: RUF001
        # ASCII-dash range
        ("Compensation: $35-$60 /hour", (Decimal(35), Decimal(60), RateUnit.HOUR, "USD")),
        # Single hourly figure — flow into both min and max
        ("Rate: $25/hr to start", (Decimal(25), Decimal(25), RateUnit.HOUR, "USD")),
        # EUR range
        ("We pay 40-60€ per hour", (Decimal(40), Decimal(60), RateUnit.HOUR, "EUR")),
        # No rate mentioned
        ("Just text with no rate", (None, None, RateUnit.UNKNOWN, None)),
        # Annual salary is NOT matched — only hourly rates feed the floor filter
        ("Salary: $120,000 per year", (None, None, RateUnit.UNKNOWN, None)),
    ],
)
def test_parse_rate_from_description(text, expected):
    assert _parse_rate_from_description(text) == expected


def test_linkedin_source_populates_derived_fields(monkeypatch):
    from jobscout.sources import linkedin as li_mod

    df = _load_fixtures_as_df()
    monkeypatch.setattr(li_mod, "_scrape", lambda **_: df)

    src = li_mod.LinkedInSource(search_terms=["test"], location="Hamburg")
    listings = src.discover()

    assert len(listings) > 0
    for listing in listings:
        assert listing.source == Source.LINKEDIN
        assert listing.apply_method in (ApplyMethod.EASY_APPLY, ApplyMethod.EXTERNAL_APPLY), listing.url
        assert listing.arrangement in tuple(Arrangement), listing.url
        assert listing.job_type_classified in tuple(JobType), listing.url
    # LinkedIn is classified optimistic EXTERNAL_APPLY (worker demotes true
    # Easy Apply to easy_apply at click time).
    assert all(listing.apply_method == ApplyMethod.EXTERNAL_APPLY for listing in listings)


def test_linkedin_source_attaches_evidence_strings(monkeypatch):
    from jobscout.sources import linkedin as li_mod

    df = _load_fixtures_as_df()
    monkeypatch.setattr(li_mod, "_scrape", lambda **_: df)

    src = li_mod.LinkedInSource(search_terms=["test"], location="Hamburg")
    listings = src.discover()

    # At least some have arrangement_evidence (hybrid/remote classifications)
    with_evidence = [listing for listing in listings if listing.arrangement_evidence]
    assert len(with_evidence) > 0

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
    for listing in listings:
        assert listing.source == Source.INDEED
        assert listing.apply_method in (ApplyMethod.EASY_APPLY, ApplyMethod.EXTERNAL_APPLY)
        assert listing.arrangement in tuple(Arrangement)
        assert listing.job_type_classified in tuple(JobType)


def test_indeed_source_split_apply_methods(monkeypatch):
    """Indeed corpus has both external_apply (company_url_direct present)
    and easy_apply (Indeed-internal) listings — make sure we see both."""
    from jobscout.sources import indeed as ind_mod

    df = _load_fixtures_as_df()
    monkeypatch.setattr(ind_mod, "_scrape", lambda **_: df)

    src = ind_mod.IndeedSource(search_terms=["test"], location="Hamburg", country="germany")
    listings = src.discover()

    methods = {listing.apply_method for listing in listings}
    assert ApplyMethod.EXTERNAL_APPLY in methods
    assert ApplyMethod.EASY_APPLY in methods

import json
from pathlib import Path

from jobscout.models import Source
from jobscout.sources.bundesagentur import BundesagenturSource

FIX = Path(__file__).parent / "fixtures" / "bundesagentur" / "sample.json"


def test_parses_fixture(monkeypatch):
    payload = json.loads(FIX.read_text())
    monkeypatch.setattr("jobscout.sources.bundesagentur._search", lambda was, **kw: payload)
    out = BundesagenturSource(search_terms=["KI Ingenieur"]).discover()
    assert all(listing.source == Source.BUNDESAGENTUR for listing in out)
    assert len(out) >= 1
    assert any(listing.remote for listing in out)

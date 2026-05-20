from pathlib import Path

from jobscout.models import Source
from jobscout.sources.freelancermap import FreelancermapSource

FIX = Path(__file__).parent / "fixtures" / "freelancermap" / "sample.html"

# Stub detail body text so discover() doesn't hit the live site during tests.
_FAKE_DETAIL_BODY = (
    "PROJEKTTITEL Senior AI Engineer\nECKDATEN Start: Mai 2026, Remote 100%.\n"
    "AUFGABEN Build RAG pipelines, LangChain, Vector DBs, evaluation harness."
)


def _patch_network(monkeypatch, *, detail_body: str = _FAKE_DETAIL_BODY) -> None:
    monkeypatch.setattr("jobscout.sources.freelancermap._fetch_page", lambda url: FIX.read_bytes())
    monkeypatch.setattr("jobscout.sources.freelancermap._fetch_detail_body", lambda url: detail_body)


def test_parses_fixture(monkeypatch):
    _patch_network(monkeypatch)
    out = FreelancermapSource(queries=["LangChain"]).discover()
    assert all(listing.source == Source.FREELANCERMAP for listing in out)
    assert len(out) >= 5  # real fixture has 22 cards
    first = out[0]
    assert first.url.startswith("https://www.freelancermap.de/projekt/")
    assert first.title  # non-empty
    # Description is built from card signals; at least keywords should be there.
    assert first.description is not None
    assert "Keywords:" in first.description or "Location:" in first.description
    assert first.language == "de"


def test_remote_threshold(monkeypatch):
    _patch_network(monkeypatch)
    out = FreelancermapSource(queries=["LangChain"]).discover()
    # The fixture has a mix of remote percentages; at least one should pass the
    # 70% threshold and at least one should fail (so the filter actually
    # discriminates).
    remote_flags = {listing.remote for listing in out}
    assert remote_flags == {True, False}, f"expected both remote and non-remote listings; got {remote_flags}"


def test_detail_body_merged_into_description(monkeypatch):
    _patch_network(monkeypatch)
    out = FreelancermapSource(queries=["LangChain"]).discover()
    # Every listing's description must contain both the card-level signals
    # (Keywords/Location prefix) AND the stub detail body that we patched in.
    assert all("AUFGABEN" in listing.description for listing in out), \
        "detail body did not get merged into description"
    # Card signals still present.
    assert any("Keywords:" in listing.description for listing in out)


def test_detail_body_failure_falls_back_to_card(monkeypatch):
    _patch_network(monkeypatch, detail_body="")
    out = FreelancermapSource(queries=["LangChain"]).discover()
    # Empty detail body → description is the card-level string only,
    # no trailing whitespace from a missing join.
    for listing in out:
        assert "AUFGABEN" not in listing.description
        assert not listing.description.endswith("\n\n")

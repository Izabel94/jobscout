from __future__ import annotations

from decimal import Decimal

from jobscout import salary as salary_mod
from jobscout.salary import _to_eur, coerce_estimate
from jobscout.ui.card import salary_display


def test_to_eur_handles_german_and_k_notation():
    assert _to_eur("55.000") == Decimal(55000)
    assert _to_eur("55000") == Decimal(55000)
    assert _to_eur(55000) == Decimal(55000)
    assert _to_eur("55k") == Decimal(55000)
    assert _to_eur("67,5k") == Decimal("67500")
    assert _to_eur("garbage") is None
    assert _to_eur("0") is None


def test_coerce_estimate_valid():
    out = coerce_estimate(
        {"found": True, "min_eur": 55000, "max_eur": 70000, "basis": "14 Kununu salaries", "confidence": "high"}
    )
    assert out == (Decimal(55000), Decimal(70000), "14 Kununu salaries", "high")


def test_coerce_estimate_confidence_defaults_low():
    out = coerce_estimate({"found": True, "min_eur": 50000, "max_eur": 60000, "basis": "regional avg"})
    assert out == (Decimal(50000), Decimal(60000), "regional avg", "low")


def test_coerce_estimate_rejects_not_found_and_inverted():
    assert coerce_estimate({"found": False, "min_eur": 50000, "max_eur": 70000}) is None
    assert coerce_estimate({"found": True, "min_eur": 90000, "max_eur": 50000, "basis": "x"}) is None
    assert coerce_estimate({"found": True, "min_eur": None, "max_eur": 70000}) is None


def test_salary_display_prefers_listed_then_estimate():
    listed = {"rate_min": 60000, "rate_max": 80000, "rate_unit": "salary"}
    assert salary_display(listed) == ("€60k-€80k/yr", "listed")

    high = {"salary_min": 55000, "salary_max": 70000, "salary_source": "kununu"}
    assert salary_display(high) == ("≈ €55k-€70k/yr", "Kununu")

    # low-confidence estimates are stored but hidden
    low = {"salary_min": 55000, "salary_max": 70000, "salary_source": "kununu_low_confidence"}
    assert salary_display(low) is None

    assert salary_display({"rate_min": None, "rate_max": None}) is None


def test_salary_main_estimates_skips_and_caches(monkeypatch):
    rows = [
        {"id": "a", "title": "Performance Marketing Manager", "raw": {"company": "Acme"}},
        {"id": "b", "title": "Performance Marketing Manager", "raw": {"company": "Acme"}},  # dup -> cache hit
        {"id": "c", "title": "Already Rated", "raw": {"company": "X"}, "rate_min": 50000},  # skip
        {"id": "d", "title": "Has Estimate", "raw": {"company": "Y"}, "salary_min": 40000},  # skip
    ]
    monkeypatch.setattr(salary_mod, "list_pipeline_listings_legacy", lambda *a, **k: rows)
    searches = {"n": 0}

    def _fake_search(query, **kw):
        searches["n"] += 1
        return [{"title": "Gehalt", "content": "Performance Marketing Manager ~55.000-70.000 EUR"}]

    monkeypatch.setattr(salary_mod, "tavily_search", _fake_search)
    monkeypatch.setattr(
        salary_mod, "call_json",
        lambda **kw: {"found": True, "min_eur": 55000, "max_eur": 70000, "basis": "Kununu", "confidence": "high"},
    )
    saved: list[tuple] = []
    monkeypatch.setattr(
        salary_mod, "set_listing_salary_estimate",
        lambda lid, *, salary_min, salary_max, note, confidence: saved.append((lid, salary_min, salary_max, confidence)),
    )

    salary_mod.main()

    assert [s[0] for s in saved] == ["a", "b"]
    assert searches["n"] == 1  # one search, reused for the duplicate role
    assert saved[0][1:] == (55000.0, 70000.0, "high")


def test_salary_main_aborts_when_search_unavailable(monkeypatch):
    from jobscout.search import SearchError

    rows = [{"id": "a", "title": "Role", "raw": {"company": "Acme"}}]
    monkeypatch.setattr(salary_mod, "list_pipeline_listings_legacy", lambda *a, **k: rows)

    def _raise(*a, **k):
        raise SearchError("TAVILY_API_KEY not set")

    monkeypatch.setattr(salary_mod, "tavily_search", _raise)
    saved: list = []
    monkeypatch.setattr(salary_mod, "set_listing_salary_estimate", lambda *a, **k: saved.append(a))

    salary_mod.main()  # must not raise
    assert saved == []

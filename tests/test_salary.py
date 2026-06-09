from __future__ import annotations

from decimal import Decimal

from jobscout import salary as salary_mod
from jobscout.salary import _to_eur, parse_salary_response
from jobscout.ui.card import salary_display


def test_to_eur_handles_german_and_k_notation():
    assert _to_eur("55.000") == Decimal(55000)
    assert _to_eur("55000") == Decimal(55000)
    assert _to_eur("55k") == Decimal(55000)
    assert _to_eur("67,5k") == Decimal("67500")
    assert _to_eur("garbage") is None
    assert _to_eur("0") is None


def test_parse_salary_response_valid():
    out = parse_salary_response("SALARY: 55.000-70.000 EUR/year | BASIS: 14 Kununu salaries, Hamburg")
    assert out is not None
    lo, hi, basis = out
    assert (lo, hi) == (Decimal(55000), Decimal(70000))
    assert "Kununu" in basis


def test_parse_salary_response_unknown_and_inverted():
    assert parse_salary_response("SALARY: UNKNOWN") is None
    assert parse_salary_response("no salary line here") is None
    # inverted range rejected
    assert parse_salary_response("SALARY: 90000-50000 EUR/year | BASIS: x") is None


def test_salary_display_prefers_listed_then_estimate():
    listed = {"rate_min": 60000, "rate_max": 80000, "rate_unit": "salary"}
    assert salary_display(listed) == ("€60k-€80k/yr", "listed")

    est = {"salary_min": 55000, "salary_max": 70000, "salary_source": "kununu_estimate"}
    assert salary_display(est) == ("≈ €55k-€70k/yr", "Kununu estimate")

    assert salary_display({"rate_min": None, "rate_max": None}) is None


def test_salary_main_estimates_skips_and_caches(monkeypatch):
    rows = [
        {"id": "a", "title": "Performance Marketing Manager", "raw": {"company": "Acme"}},
        {"id": "b", "title": "Performance Marketing Manager", "raw": {"company": "Acme"}},  # dup -> cache hit
        {"id": "c", "title": "Already Rated", "raw": {"company": "X"}, "rate_min": 50000},  # skip
        {"id": "d", "title": "Has Estimate", "raw": {"company": "Y"}, "salary_min": 40000},  # skip
    ]
    monkeypatch.setattr(salary_mod, "list_pipeline_listings_legacy", lambda *a, **k: rows)
    calls = {"n": 0}

    def _fake_grounded(**kw):
        calls["n"] += 1
        return "SALARY: 55.000-70.000 EUR/year | BASIS: Kununu"

    monkeypatch.setattr(salary_mod, "call_grounded", _fake_grounded)
    saved: list[tuple] = []
    monkeypatch.setattr(
        salary_mod, "set_listing_salary_estimate",
        lambda lid, *, salary_min, salary_max, note: saved.append((lid, salary_min, salary_max)),
    )

    salary_mod.main()

    # a and b saved (b via cache, no extra lookup); c and d skipped.
    assert [s[0] for s in saved] == ["a", "b"]
    assert calls["n"] == 1  # one grounded lookup, reused for the duplicate role
    assert saved[0][1:] == (55000.0, 70000.0)

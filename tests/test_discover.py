"""Tests for discover-stage search term derivation."""

from __future__ import annotations


def test_derive_search_terms_from_profile(monkeypatch) -> None:
    from jobscout import discover as disc

    monkeypatch.setattr(
        disc,
        "load_profile",
        lambda: {
            "required_skill_keywords": ["LLM", "RAG", "LangChain", "Python"],
            "headline": "ML Engineer at FooCorp",
            "skills": [],
        },
    )
    terms = disc._derive_search_terms()
    assert len(terms) <= 5
    assert "LLM" in terms or any("LLM" in t for t in terms)


def test_derive_search_terms_falls_back_when_no_profile(monkeypatch) -> None:
    from jobscout import discover as disc

    def _raise() -> dict[str, object]:
        raise RuntimeError("no profile")

    monkeypatch.setattr(disc, "load_profile", _raise)
    terms = disc._derive_search_terms()
    assert all("freelance" not in t.lower() and "contract" not in t.lower() for t in terms)
    assert len(terms) > 0


def test_derive_search_terms_uses_skills_when_keywords_thin(monkeypatch) -> None:
    from jobscout import discover as disc

    monkeypatch.setattr(
        disc,
        "load_profile",
        lambda: {
            "required_skill_keywords": ["LLM"],
            "headline": "Senior Data Scientist",
            "skills": ["Python", "PyTorch", "Pandas"],
        },
    )
    terms = disc._derive_search_terms()
    # Should pair tokens with the role from headline ("Scientist")
    assert any("Scientist" in t for t in terms)

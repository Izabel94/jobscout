"""Unit tests for the freshness checker — monkeypatches httpx."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from jobscout.freshness import is_listing_alive
from jobscout.models import Source


@dataclass
class _StubResp:
    status_code: int
    text: str = ""


def _patch_httpx(monkeypatch, status_code: int = 200, body: str = "", raises: Exception | None = None) -> None:
    class _StubClient:
        def __init__(self, **kw: Any) -> None:
            pass

        def __enter__(self) -> _StubClient:
            return self

        def __exit__(self, *exc: Any) -> None:
            return None

        def get(self, url: str) -> _StubResp:
            if raises is not None:
                raise raises
            return _StubResp(status_code=status_code, text=body)

    monkeypatch.setattr("jobscout.freshness.httpx.Client", _StubClient)


def test_linkedin_closed_job_is_dead(monkeypatch) -> None:
    _patch_httpx(monkeypatch, 200, '<html><div class="job__flavor--closed">No longer accepting</div></html>')
    assert is_listing_alive("https://linkedin.com/jobs/view/123", Source.LINKEDIN.value) is False


def test_linkedin_open_job_is_alive(monkeypatch) -> None:
    _patch_httpx(monkeypatch, 200, "<html><h1>Senior AI Engineer</h1></html>")
    assert is_listing_alive("https://linkedin.com/jobs/view/456", Source.LINKEDIN.value) is True


def test_404_is_dead(monkeypatch) -> None:
    _patch_httpx(monkeypatch, 404, "")
    assert is_listing_alive("https://linkedin.com/jobs/view/404", Source.LINKEDIN.value) is False


def test_network_error_returns_none(monkeypatch) -> None:
    """Inconclusive results must NOT be confused with 'dead'."""
    _patch_httpx(monkeypatch, raises=httpx.ConnectTimeout("timeout"))
    assert is_listing_alive("https://linkedin.com/jobs/view/timeout", Source.LINKEDIN.value) is None


def test_unsupported_source_returns_none() -> None:
    """Upwork isn't covered yet — must return None, not crash."""
    assert is_listing_alive("https://upwork.com/jobs/~01abc/", Source.UPWORK.value) is None


def test_freelancermap_closed_job(monkeypatch) -> None:
    _patch_httpx(monkeypatch, 200, "<html>Projekt nicht mehr aktuell</html>")
    assert is_listing_alive("https://freelancermap.de/projekt/foo", Source.FREELANCERMAP.value) is False


def test_bundesagentur_closed_job(monkeypatch) -> None:
    _patch_httpx(monkeypatch, 200, "<html>Stellenangebot nicht mehr verfügbar</html>")
    assert is_listing_alive("https://arbeitsagentur.de/jobsuche/jobdetail/123", Source.BUNDESAGENTUR.value) is False


def test_marker_compiled_for_every_known_source() -> None:
    """Sanity: when we add a new source, freshness coverage shouldn't regress."""
    from jobscout.freshness import _DEAD_MARKERS

    # Sources we deliberately don't cover yet (login-walled).
    excluded = {Source.UPWORK.value}
    for source in Source:
        if source.value in excluded:
            continue
        assert source.value in _DEAD_MARKERS, f"no freshness marker for source={source.value}"

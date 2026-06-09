"""Thin Tavily web-search client. Used by the salary stage to fetch Kununu
results, which a plain LLM call then distils into a range. Kept separate from
llm.py because it's a search provider, not a model."""

from __future__ import annotations

import os
from typing import Any

import httpx

_TAVILY_URL = "https://api.tavily.com/search"


class SearchError(RuntimeError):
    """Search provider unavailable or failed (missing key, network, non-2xx)."""


def tavily_search(query: str, *, include_domains: list[str] | None = None, max_results: int = 5) -> list[dict[str, Any]]:
    """Return Tavily result dicts ({title, url, content, ...}). Raises SearchError
    on a missing key or a failed request."""
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        raise SearchError("TAVILY_API_KEY not set")
    payload: dict[str, Any] = {
        "api_key": key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
    }
    if include_domains:
        payload["include_domains"] = include_domains
    try:
        resp = httpx.post(_TAVILY_URL, json=payload, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise SearchError(f"Tavily request failed: {e}") from e
    results = resp.json().get("results", [])
    return results if isinstance(results, list) else []

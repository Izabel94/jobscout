"""Salary stage: estimate a salary range for listings that don't state one.
German full-time postings almost never publish salary, so this is the primary
salary signal. Searches Kununu via Tavily, then a plain Gemini call distils the
result snippets into a range.

Runs after filter (only surviving listings cost a lookup) and caches by
(company, normalized title) so duplicate roles don't re-query.
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from jobscout.db import (
    list_pipeline_listings_legacy,
    mark_listing_salary_unavailable,
    set_listing_salary_estimate,
)
from jobscout.llm import LLMJSONError, call_json
from jobscout.models import ListingStatus
from jobscout.search import SearchError, tavily_search

log = logging.getLogger("salary")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_MODEL = "gemini-3.1-flash-lite"
_ACTIVE_STATUSES = [ListingStatus.NEW, ListingStatus.SCORED, ListingStatus.DRAFTED]
_CITY = "Hamburg"  # Julian's search is Hamburg-only

_EXTRACT_SYSTEM = (
    "You extract salary data from German web-search snippets (kununu.com). "
    "Return STRICT JSON only, no prose."
)
_EXTRACT_USER = (
    "Role: {title}\nCompany: {company}\nCity: {city}, Germany\n\n"
    "From these kununu.com search snippets, give the typical annual GROSS salary "
    "range in EUR for this role.\n"
    "Snippets:\n---\n{snippets}\n---\n\n"
    'Return strict JSON: {{"found": true|false, "min_eur": <number|null>, '
    '"max_eur": <number|null>, "basis": "<short basis>", "confidence": "high"|"low"}}.\n'
    'Set confidence="high" ONLY when the snippets give a Kununu salary for THIS '
    "company, at a matching seniority (a Senior role needs senior data). Use "
    '"low" for any regional/role average, a different seniority, or an '
    "extrapolation. Set found=false if there is no usable salary figure at all. "
    "Respect seniority: never report a junior/mid range for a Senior title."
)


def _to_eur(value: Any) -> Decimal | None:
    """Coerce '55.000', '55000', 55000, '55k', '67,5k' -> Decimal EUR."""
    s = str(value).strip().lower().replace(" ", "").replace("€", "")
    mult = Decimal(1)
    if s.endswith("k"):
        mult = Decimal(1000)
        s = s[:-1]
    s = s.replace(".", "").replace(",", ".")  # German thousands '.', decimal ','
    try:
        out = Decimal(s) * mult
    except (InvalidOperation, ValueError):
        return None
    return out if out > 0 else None


def coerce_estimate(data: dict[str, Any]) -> tuple[Decimal, Decimal, str, str] | None:
    """Validate the extractor's JSON into (min, max, basis, confidence), or None.
    confidence is 'high' only when the model is confident; anything else -> 'low'."""
    if not data.get("found"):
        return None
    lo, hi = _to_eur(data.get("min_eur")), _to_eur(data.get("max_eur"))
    if lo is None or hi is None or lo > hi:
        return None
    basis = str(data.get("basis") or "Kununu estimate")[:200]
    confidence = "high" if str(data.get("confidence", "")).lower() == "high" else "low"
    return lo, hi, basis, confidence


def _lookup(title: str, company: str) -> tuple[Decimal, Decimal, str, str] | None:
    query = f"{title} {company} {_CITY} Gehalt Jahresgehalt"
    results = tavily_search(query, include_domains=["kununu.com"], max_results=5)
    if not results:
        return None
    snippets = "\n\n".join(f"{r.get('title', '')}\n{r.get('content', '')}" for r in results)[:4000]
    user = _EXTRACT_USER.format(title=title, company=company or "(unknown)", city=_CITY, snippets=snippets)
    try:
        data = call_json(model=_MODEL, system=_EXTRACT_SYSTEM, user=user)
    except LLMJSONError:
        return None
    return coerce_estimate(data)


def main() -> None:
    rows = list_pipeline_listings_legacy(_ACTIVE_STATUSES, limit=10_000)
    cache: dict[tuple[str, str], tuple[Decimal, Decimal, str, str] | None] = {}
    estimated = 0
    for row in rows:
        if row.get("rate_min") or row.get("rate_max") or row.get("salary_min") or row.get("salary_source"):
            continue  # already has a listed rate, a prior estimate, or a prior Kununu attempt
        company = str((row.get("raw") or {}).get("company") or "")
        title = row.get("title") or ""
        key = (company.lower().strip(), " ".join(title.lower().split()))
        if key not in cache:
            try:
                cache[key] = _lookup(title, company)
            except SearchError as e:
                log.warning("search unavailable, stopping salary stage: %s", e)
                break
        result = cache[key]
        if result is None:
            mark_listing_salary_unavailable(row["id"])
            continue
        lo, hi, basis, confidence = result
        set_listing_salary_estimate(
            row["id"], salary_min=float(lo), salary_max=float(hi), note=basis, confidence=confidence
        )
        if confidence == "high":
            estimated += 1
    log.info("salary: %d high-confidence estimate(s) from %d lookup(s)", estimated, len(cache))


if __name__ == "__main__":
    main()

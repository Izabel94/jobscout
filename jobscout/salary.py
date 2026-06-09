"""Salary stage: estimate a salary range from Kununu for listings that don't
state one. German full-time postings almost never publish salary, so this is
the primary salary signal. Uses Gemini grounded Google Search scoped to Kununu.

Runs after filter (only surviving listings cost a call) and caches by
(company, normalized title) so duplicate roles don't re-query.
"""

import logging
import re
from decimal import Decimal, InvalidOperation

from jobscout.db import list_pipeline_listings_legacy, set_listing_salary_estimate
from jobscout.llm import LLMProviderError, call_grounded
from jobscout.models import ListingStatus

log = logging.getLogger("salary")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_MODEL = "gemini-3.1-flash-lite"
_ACTIVE_STATUSES = [ListingStatus.NEW, ListingStatus.SCORED, ListingStatus.DRAFTED]
_CITY = "Hamburg"  # Julian's search is Hamburg-only

_SYSTEM = (
    "You are a salary research assistant. Use Google Search over kununu.com — a "
    "German employer-review site with salary data (Gehalt) — to find the typical "
    "annual GROSS salary (Bruttojahresgehalt, EUR) for a role. Prefer the named "
    "company; if it is not on Kununu, use similar roles at comparable companies in "
    "the given city. Be conservative and cite a realistic range, not a single point."
)
_USER_TMPL = (
    "Role: {title}\n"
    "Company: {company}\n"
    "City: {city}, Germany\n\n"
    "Find the typical annual gross salary range in EUR for this role per kununu.com.\n"
    "Respond with EXACTLY ONE line and no other prose:\n"
    "SALARY: <min>-<max> EUR/year | BASIS: <short basis>\n"
    "If you cannot find any usable data, respond exactly: SALARY: UNKNOWN"
)

# The char class covers hyphen, en dash, and em dash: the grounded model emits
# any of them in a range. The non-ASCII dashes are intentional, hence the noqa.
_RANGE_RE = re.compile(r"SALARY:\s*([\d.,kK]+)\s*[-–—]\s*([\d.,kK]+)\s*EUR", re.I)  # noqa: RUF001
_BASIS_RE = re.compile(r"BASIS:\s*(.+?)\s*$", re.I | re.M)


def _to_eur(token: str) -> Decimal | None:
    """Parse a salary figure: '55.000', '55000', '55k', '55,5k' -> Decimal EUR."""
    s = token.strip().lower().replace(" ", "").replace("€", "")
    mult = Decimal(1)
    if s.endswith("k"):
        mult = Decimal(1000)
        s = s[:-1]
    # German thousands use '.', decimals use ',': drop dots, swap comma to dot.
    s = s.replace(".", "").replace(",", ".")
    try:
        value = Decimal(s) * mult
    except (InvalidOperation, ValueError):
        return None
    return value if value > 0 else None


def parse_salary_response(text: str) -> tuple[Decimal, Decimal, str] | None:
    """Parse the grounded model's one-line answer into (min, max, basis).
    Returns None on UNKNOWN / unparseable / inverted ranges."""
    m = _RANGE_RE.search(text or "")
    if not m:
        return None
    lo, hi = _to_eur(m.group(1)), _to_eur(m.group(2))
    if lo is None or hi is None or lo > hi:
        return None
    basis_m = _BASIS_RE.search(text)
    basis = basis_m.group(1).strip() if basis_m else "Kununu estimate"
    return lo, hi, basis


def _lookup(title: str, company: str) -> tuple[Decimal, Decimal, str] | None:
    user = _USER_TMPL.format(title=title, company=company or "(unknown)", city=_CITY)
    text = call_grounded(model=_MODEL, system=_SYSTEM, user=user)
    return parse_salary_response(text)


def main() -> None:
    rows = list_pipeline_listings_legacy(_ACTIVE_STATUSES, limit=10_000)
    cache: dict[tuple[str, str], tuple[Decimal, Decimal, str] | None] = {}
    estimated = 0
    for row in rows:
        if row.get("rate_min") or row.get("rate_max") or row.get("salary_min"):
            continue  # already has a listed rate or a prior estimate
        company = str((row.get("raw") or {}).get("company") or "")
        title = row.get("title") or ""
        key = (company.lower().strip(), " ".join(title.lower().split()))
        if key not in cache:
            try:
                cache[key] = _lookup(title, company)
            except LLMProviderError as e:
                # Grounding unavailable (e.g. quota/billing) — abort rather than
                # retry-hang on every remaining listing.
                log.warning("grounded lookup failed, stopping salary stage: %s", e)
                break
        result = cache[key]
        if result is None:
            continue
        lo, hi, basis = result
        set_listing_salary_estimate(row["id"], salary_min=float(lo), salary_max=float(hi), note=basis)
        estimated += 1
    log.info("salary: estimated %d listing(s) from %d lookup(s)", estimated, len(cache))


if __name__ == "__main__":
    main()

import re
from decimal import Decimal
from typing import Any

import pandas as pd
from jobspy import scrape_jobs

from jobscout.derive import classify_apply_method, classify_arrangement, classify_job_type
from jobscout.models import Listing, RateUnit, Source
from jobscout.sources.base import BRAND_UA, CadenceRule, SourceAdapter

_JSON_SAFE_TYPES = (str, int, float, bool, list, dict, type(None))

# JobSpy doesn't surface LinkedIn rate as a field — extract from description
# prose. Range regex must precede single-rate regex (else "$35-$60/hr" matches
# the single twice). Require explicit hourly unit — bare numbers are ambiguous.
_HOURLY_HINT_RE = re.compile(r"(?:/|\s+per\s+)\s*(?:hour|hr|h\b)", re.I)
_RANGE_USD_HOURLY_RE = re.compile(
    r"\$\s*(\d{1,4}(?:[.,]\d{1,2})?)\s*[-–—]\s*\$?\s*(\d{1,4}(?:[.,]\d{1,2})?)"  # noqa: RUF001
    r"\s*(?:/|\s+per\s+)\s*(?:hour|hr|h\b)",
    re.I,
)
_SINGLE_USD_HOURLY_RE = re.compile(
    r"\$\s*(\d{1,4}(?:[.,]\d{1,2})?)\s*(?:/|\s+per\s+)\s*(?:hour|hr|h\b)",
    re.I,
)
_RANGE_EUR_HOURLY_RE = re.compile(
    r"(\d{1,4}(?:[.,]\d{1,2})?)\s*[-–—]\s*(\d{1,4}(?:[.,]\d{1,2})?)\s*€"  # noqa: RUF001
    r"\s*(?:/|\s+per\s+)\s*(?:hour|hr|stunde|h\b)",
    re.I,
)
_SINGLE_EUR_HOURLY_RE = re.compile(
    r"(\d{1,4}(?:[.,]\d{1,2})?)\s*€\s*(?:/|\s+per\s+)\s*(?:hour|hr|stunde|h\b)",
    re.I,
)


def _to_decimal(s: str) -> Decimal:
    return Decimal(s.replace(",", "."))


def _parse_rate_from_description(text: str) -> tuple[Decimal | None, Decimal | None, RateUnit, str | None]:
    """Returns (min, max, unit, currency). Unit is always HOUR — daily/annual rates aren't reliably distinguishable from bare numbers."""
    if not text:
        return None, None, RateUnit.UNKNOWN, None
    m = _RANGE_USD_HOURLY_RE.search(text)
    if m:
        return _to_decimal(m.group(1)), _to_decimal(m.group(2)), RateUnit.HOUR, "USD"
    m = _RANGE_EUR_HOURLY_RE.search(text)
    if m:
        return _to_decimal(m.group(1)), _to_decimal(m.group(2)), RateUnit.HOUR, "EUR"
    m = _SINGLE_USD_HOURLY_RE.search(text)
    if m:
        v = _to_decimal(m.group(1))
        return v, v, RateUnit.HOUR, "USD"
    m = _SINGLE_EUR_HOURLY_RE.search(text)
    if m:
        v = _to_decimal(m.group(1))
        return v, v, RateUnit.HOUR, "EUR"
    return None, None, RateUnit.UNKNOWN, None


def _scrape(**kwargs: Any) -> pd.DataFrame:
    df: pd.DataFrame = scrape_jobs(**kwargs)
    return df


def _safe_raw(d: dict[str, Any]) -> dict[str, Any]:
    """Coerce numpy/pandas scalars to JSON-safe types."""
    safe: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, _JSON_SAFE_TYPES):
            safe[str(k)] = v
        else:
            safe[str(k)] = str(v)
    return safe


class LinkedInSource(SourceAdapter):
    source = Source.LINKEDIN

    def __init__(self, search_terms: list[str], location: str = "Germany") -> None:
        self.search_terms = search_terms
        self.location = location
        self.policy = CadenceRule(jitter_pct=40.0, ua=BRAND_UA, max_results_per_run=15)

    def discover(self) -> list[Listing]:
        out: list[Listing] = []
        for term in self.search_terms:
            df = _scrape(
                site_name=["linkedin"],
                search_term=term,
                location=self.location,
                results_wanted=self.policy.max_results_per_run or 15,
                hours_old=72,
                is_remote=True,
                job_type="contract",
                linkedin_fetch_description=True,
            )
            for _, row in df.iterrows():
                d: dict[str, Any] = row.to_dict()
                # Company denylist deferred — re-introduce in Phase 4 from profiles.title_denylist.
                description = str(d.get("description") or "")
                rate_min, rate_max, rate_unit, currency = _parse_rate_from_description(description)
                arrangement, arr_ev = classify_arrangement(d)
                job_type_classified, jt_ev = classify_job_type(d)
                apply_method, _am_ev = classify_apply_method("linkedin", d)
                out.append(
                    Listing(
                        source=Source.LINKEDIN,
                        source_id=str(d.get("id") or d["job_url"]),
                        url=str(d["job_url"]),
                        title=str(d["title"]),
                        description=description,
                        location=str(d.get("location") or ""),
                        remote=bool(d.get("is_remote")),
                        language="en",
                        rate_min=rate_min,
                        rate_max=rate_max,
                        rate_unit=rate_unit,
                        currency=currency,
                        arrangement=arrangement,
                        arrangement_evidence=arr_ev,
                        job_type_classified=job_type_classified,
                        job_type_evidence=jt_ev,
                        apply_method=apply_method,
                        raw=_safe_raw(d),
                    )
                )
            self.sleep_jitter(3.0)
        return out

"""Indeed search scraper, JobSpy-backed.

Hamburg-region only. JobSpy uses Indeed's mobile API (no login needed).
work_from_home_type is the Indeed-specific signal for arrangement —
classify_arrangement prefers it when populated. company_url_direct drives
apply_method (present → EXTERNAL_APPLY).
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from jobspy import scrape_jobs

from jobscout.derive import classify_apply_method, classify_arrangement, classify_job_type
from jobscout.models import Listing, RateUnit, Source
from jobscout.sources._description import html_to_markdown
from jobscout.sources.base import BRAND_UA, CadenceRule, SourceAdapter

_JSON_SAFE_TYPES = (str, int, float, bool, list, dict, type(None))


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


class IndeedSource(SourceAdapter):
    source = Source.INDEED

    def __init__(
        self,
        search_terms: list[str],
        location: str = "Hamburg, Germany",
        country: str = "germany",
    ) -> None:
        self.search_terms = search_terms
        self.location = location
        self.country = country
        self.policy = CadenceRule(jitter_pct=40.0, ua=BRAND_UA, max_results_per_run=15)

    def discover(self) -> list[Listing]:
        out: list[Listing] = []
        for term in self.search_terms:
            df = _scrape(
                site_name=["indeed"],
                search_term=term,
                location=self.location,
                country_indeed=self.country,
                results_wanted=self.policy.max_results_per_run or 15,
                hours_old=72,
                description_format="html",
            )
            for _, row in df.iterrows():
                d: dict[str, Any] = row.to_dict()
                description = html_to_markdown(d.get("description"))
                arrangement, arr_ev = classify_arrangement(d)
                job_type_classified, jt_ev = classify_job_type(d)
                apply_method, _am_ev = classify_apply_method("indeed", d)
                out.append(
                    Listing(
                        source=Source.INDEED,
                        source_id=str(d.get("id") or d["job_url"]),
                        url=str(d["job_url"]),
                        title=str(d["title"]),
                        description=description,
                        location=str(d.get("location") or ""),
                        remote=bool(d.get("is_remote")),
                        language=None,
                        rate_min=None,
                        rate_max=None,
                        rate_unit=RateUnit.UNKNOWN,
                        currency=None,
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

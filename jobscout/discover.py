"""Discover stage of the daily pipeline (cron entrypoint)."""

import argparse
import logging
import re
import traceback

from jobscout.config_loader import load_profile
from jobscout.db import log_source_run, upsert_listing
from jobscout.sources.indeed import IndeedSource
from jobscout.sources.linkedin import LinkedInSource

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("discover")

_LOCATION = "Hamburg"
_MAX_TERMS = 5
_ROLE_TOKEN_RE = re.compile(
    r"\b(engineer|scientist|developer|architect|manager|designer|analyst|consultant)\b",
    re.I,
)
_FALLBACK_SEARCH_TERMS = [
    "Software Engineer",
    "Data Scientist",
    "Machine Learning Engineer",
    "Python Developer",
    "Backend Engineer",
]

_SOURCES = {
    "linkedin": LinkedInSource,
    "indeed": IndeedSource,
}


def _derive_search_terms() -> list[str]:
    try:
        profile = load_profile()
    except RuntimeError:
        return _FALLBACK_SEARCH_TERMS

    keywords = list(profile.get("required_skill_keywords") or [])
    headline = profile.get("headline") or ""
    role_match = _ROLE_TOKEN_RE.search(headline)
    role = role_match.group(0) if role_match else "Engineer"

    if len(keywords) >= 3:
        terms = keywords[:_MAX_TERMS]
    else:
        skills = list(profile.get("skills") or [])
        seeds = (keywords + skills)[:_MAX_TERMS]
        terms = [f"{s} {role}".strip() for s in seeds]

    if not terms:
        return _FALLBACK_SEARCH_TERMS
    return terms[:_MAX_TERMS]


def _sources_to_run(only: list[str] | None) -> list[object]:
    def included(n: str) -> bool:
        return only is None or n in only

    search_terms = _derive_search_terms()
    log.info("discover search terms: %s", search_terms)

    sources: list[object] = []
    if included("linkedin"):
        sources.append(LinkedInSource(search_terms=search_terms, location=_LOCATION))
    if included("indeed"):
        sources.append(IndeedSource(search_terms=search_terms, location=_LOCATION))
    return sources


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=["linkedin", "indeed"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    for source_adapter in _sources_to_run(args.only):
        name = source_adapter.source.value  # type: ignore[attr-defined]
        log.info("running source: %s", name)
        new_count = 0
        try:
            listings = source_adapter.discover()  # type: ignore[attr-defined]
            if args.limit:
                listings = listings[: args.limit]
            for listing in listings:
                if args.dry_run:
                    log.info("[dry-run] %s | %s", listing.source.value, listing.title[:80])
                    continue
                upsert_listing(listing)
                new_count += 1
            if not args.dry_run:
                log_source_run(name, len(listings), new_count)
        except Exception as exc:
            log.error("source %s failed: %s", name, traceback.format_exc())
            if not args.dry_run:
                log_source_run(name, 0, 0, error=str(exc))


if __name__ == "__main__":
    main()

"""Discover stage of the daily pipeline (cron entrypoint)."""

import argparse
import logging
import traceback

from jobscout.db import log_source_run, upsert_listing
from jobscout.sources.indeed import IndeedSource
from jobscout.sources.linkedin import LinkedInSource

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("discover")

# TODO(Task 16): replace hardcoded defaults with DB-driven config from profiles row.
_DEFAULT_SEARCH_TERMS = [
    "AI engineer freelance",
    "LLM engineer contract",
    "LangChain contract",
    "LangGraph contract",
    "RAG engineer contract",
]
_DEFAULT_LOCATION = "Hamburg"

_SOURCES = {
    "linkedin": LinkedInSource,
    "indeed": IndeedSource,
}


def _sources_to_run(only: list[str] | None) -> list[object]:
    def included(n: str) -> bool:
        return only is None or n in only

    sources: list[object] = []
    if included("linkedin"):
        sources.append(LinkedInSource(search_terms=_DEFAULT_SEARCH_TERMS))
    if included("indeed"):
        sources.append(IndeedSource(search_terms=_DEFAULT_SEARCH_TERMS, location=_DEFAULT_LOCATION))
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

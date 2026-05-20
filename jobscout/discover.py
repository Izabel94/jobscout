"""Discover stage of the daily pipeline (cron entrypoint)."""

import argparse
import logging
import os
import traceback

from jobscout.db import log_source_run, upsert_listing

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("discover")


def _sources_to_run(only: list[str] | None) -> list[object]:
    def included(n: str) -> bool:
        return only is None or n in only

    sources: list[object] = []
    # Legacy `UPWORK_SAVED_SEARCH_URLS` kept as fallback; the current var wins if both are set.
    upwork_raw = os.environ.get("UPWORK_SEARCH_URLS") or os.environ.get("UPWORK_SAVED_SEARCH_URLS") or ""
    upwork_urls = [u.strip() for u in upwork_raw.split(",") if u.strip()]
    upwork_headless = os.environ.get("UPWORK_HEADLESS", "1") not in ("0", "false", "False")
    upwork_cdp_url = os.environ.get("UPWORK_CDP_URL") or None
    if included("upwork") and upwork_urls:
        # Lazy import: UpworkSource pulls playwright_stealth, which crawl4ai's
        # tf-playwright-stealth shadows in cron. Keep it off the import graph
        # when Upwork isn't requested.
        from jobscout.sources.upwork import UpworkSource

        sources.append(UpworkSource(search_urls=upwork_urls, headless=upwork_headless, cdp_url=upwork_cdp_url))
    if included("bundesagentur"):
        from jobscout.sources.bundesagentur import BundesagenturSource

        sources.append(BundesagenturSource(search_terms=["KI Ingenieur", "LLM", "LangChain", "RAG"]))
    if included("freelancermap"):
        from jobscout.sources.freelancermap import FreelancermapSource

        sources.append(FreelancermapSource(queries=["LangChain", "RAG", "LLM"]))
    if included("linkedin"):
        from jobscout.sources.linkedin import LinkedInSource

        sources.append(
            LinkedInSource(
                search_terms=[
                    "AI engineer freelance",
                    "LLM engineer contract",
                    "LangChain contract",
                    "LangGraph contract",
                    "RAG engineer contract",
                    "vector database freelance",
                    "semantic search freelance",
                    "LangSmith",
                ]
            )
        )
    return sources


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
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

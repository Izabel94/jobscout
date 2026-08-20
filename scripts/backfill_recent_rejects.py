"""Requeue recently-rejected listings so the fixed filter reconsiders them.

Many on-target roles were wrongly rejected by the old verbatim skill-match.
This flips rejects from the last N days back to status='new' (clearing the
workflow fields) so the next filter -> score -> draft run re-evaluates them
with the current rules. True negatives get re-rejected; survivors resurface.

Run AFTER the filter fixes are deployed, then trigger the daily workflow
(or run filter/score/draft) so the cloud pipeline reprocesses the queue.

Usage:
    poetry run dotenv run -- python scripts/backfill_recent_rejects.py --dry-run
    poetry run dotenv run -- python scripts/backfill_recent_rejects.py --days 30
"""

import argparse
from datetime import UTC, datetime, timedelta

from jobscout.db import _client


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30, help="how far back to requeue (default 30)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cutoff = (datetime.now(UTC) - timedelta(days=args.days)).isoformat()
    client = _client()

    matching = (
        client.table("listings")
        .select("id", count="exact")
        .eq("status", "rejected")
        .gte("discovered_at", cutoff)
        .execute()
    )
    n = matching.count or 0
    print(f"{n} rejected listing(s) discovered since {cutoff[:10]} would be requeued.")
    if args.dry_run or n == 0:
        return

    client.table("listings").update({"status": "new", "score": None, "score_rationale": None, "spam_score": None}).eq(
        "status", "rejected"
    ).gte("discovered_at", cutoff).execute()
    print(f"Requeued {n} listing(s) to status='new'. Run the daily pipeline to reprocess.")


if __name__ == "__main__":
    main()

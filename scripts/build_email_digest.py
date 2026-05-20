"""Build a plain-text digest of new high-scoring listings.

Emitted to stdout for the `dawidd6/action-send-mail` step in
.github/workflows/daily.yml. Reads from cloud Supabase (SUPABASE_URL +
SUPABASE_SERVICE_ROLE_KEY in env) and prints a digest with:
  - whether the upstream cron failed (UPSTREAM_FAILED env)
  - listings scored >= NOTIFY_SCORE_FLOOR in the last NOTIFY_HOURS_BACK
  - per-source counts for ingestion volume
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from jobscout.db import _client


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def main() -> int:
    upstream_failed = os.environ.get("UPSTREAM_FAILED", "").lower() == "true"
    score_floor = _env_int("NOTIFY_SCORE_FLOOR", 70)
    hours_back = _env_int("NOTIFY_HOURS_BACK", 26)

    cutoff = (datetime.now(tz=UTC) - timedelta(hours=hours_back)).isoformat()

    print("jobscout daily digest")
    print("=" * 50)
    if upstream_failed:
        print("⚠️  ONE OR MORE UPSTREAM JOBS FAILED — check the GitHub Actions run for the trace.")
        print()

    # New high-scoring listings since the cutoff
    res = (
        _client()
        .table("listings")
        .select("title,source,score,status,url,score_rationale,discovered_at")
        .gte("score", score_floor)
        .gte("discovered_at", cutoff)
        .order("score", desc=True)
        .execute()
    )
    rows = res.data or []
    print(f"NEW LISTINGS scoring ≥ {score_floor} in the last {hours_back}h: {len(rows)}")
    print()
    if not rows:
        print("(nothing surfaced — either no new listings today, or they all scored below the floor)")
    else:
        for r in rows:
            print(f"  [{r['score']:3d}] [{r['source']:14s}] [{r['status']:8s}] {r['title']}")
            url = r.get("url") or ""
            if url:
                print(f"        {url}")
            rationale = (r.get("score_rationale") or "").replace("\n", " ").strip()
            if rationale:
                print(f"        why: {rationale[:280]}")
            print()

    # Per-source ingestion counts (from source_runs) since cutoff
    print("-" * 50)
    print("INGESTION VOLUME (last 26h)")
    runs = (
        _client()
        .table("source_runs")
        .select("source,listings_found,listings_new,error,started_at")
        .gte("started_at", cutoff)
        .order("started_at", desc=True)
        .execute()
    )
    by_source: dict[str, dict[str, int | str]] = {}
    for run in runs.data or []:
        s = run.get("source") or "?"
        bucket = by_source.setdefault(s, {"runs": 0, "found": 0, "new": 0, "errors": 0, "last_error": ""})
        bucket["runs"] = int(bucket["runs"]) + 1
        bucket["found"] = int(bucket["found"]) + (run.get("listings_found") or 0)
        bucket["new"] = int(bucket["new"]) + (run.get("listings_new") or 0)
        if run.get("error"):
            bucket["errors"] = int(bucket["errors"]) + 1
            bucket["last_error"] = str(run["error"])[:160]

    if not by_source:
        print("  no source_runs recorded — cron may not have started successfully")
    else:
        for source in sorted(by_source):
            stats = by_source[source]
            line = f"  {source:14s}  runs={stats['runs']}  found={stats['found']}  new={stats['new']}"
            if stats["errors"]:
                line += f"  ⚠ errors={stats['errors']}"
            print(line)
            if stats.get("last_error"):
                print(f"      last error: {stats['last_error']}")
    print()
    print("-" * 50)
    print("Dashboard: open Streamlit locally with `make ui` to review + draft.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

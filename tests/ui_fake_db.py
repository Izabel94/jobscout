"""In-memory stand-in for the DB functions the Pipeline UI calls.

Shared by the AppTest tests and the browser e2e app, so both drive the real UI code
against the same fake. Only the DB boundary is replaced.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import jobscout.cv_render as cv_render
import jobscout.db as db
import jobscout.draft as draft
import jobscout.ui.card as card
import jobscout.ui.pipeline as pipeline
import jobscout.ui.settings as settings

_TITLES = [
    "Solutions Consultant",
    "Demand Growth Manager (f/m/d)",
    "Marketing Manager (m/w/d)",
    "Omnichannel Key Account Manager ERT / Mediamarkt Alps (AT/CH) (m/w/d)",
    "Key Account Manager Senior w/m/d - Strategic Sales Enterprise",
    "(Senior) Revenue Operations Manager (d/m/w)",
]


def make_listing(lid: str, title: str, score: int = 85) -> dict[str, Any]:
    return {
        "id": lid,
        "title": title,
        "status": "scored",
        "score": score,
        "source": "linkedin",
        "source_id": lid,
        "url": f"https://example.com/{lid}",
        "location": "Hamburg, Hamburg, Germany",
        "apply_method": "external_apply",
        "raw": {"company": f"Company {lid.upper()}"},
        "viewed_at": None,
        "bookmarked": False,
        "score_rationale": f"why {lid}",
        "description": f"description {lid}",
    }


def sample_listings(n: int) -> list[dict[str, Any]]:
    """n listings with real-length titles, mixed scores, one with a listed salary."""
    rows = [make_listing(f"l{i}", _TITLES[i % len(_TITLES)], score=95 - (i * 7) % 40) for i in range(n)]
    rows[1].update(rate_min=60000, rate_max=75000, rate_unit="salary")
    rows[3].update(
        apply_block_reason="login_wall", raw={"company": "Company L3", "job_url_direct": "https://ats.example/l3"}
    )
    rows[4].update(apply_method="easy_apply")
    return rows


def make_draft(lid: str) -> dict[str, Any]:
    return {"id": f"d-{lid}", "body": "Sehr geehrte Damen und Herren", "adapted_cv": "# CV", "model": "m"}


class FakeDB:
    def __init__(self, listings: list[dict[str, Any]]) -> None:
        self.listings = listings
        self.drafts: dict[str, dict[str, Any]] = {}
        self.writes: list[tuple[Any, ...]] = []
        self.profile: dict[str, Any] = {
            "full_name": "Test Person",
            "required_skill_keywords": ["Solutions Consultant", "Account Manager"],
            "title_denylist": ["Performance Marketing"],
            "arrangement_preferences": ["hybrid", "remote"],
            "scorer_notes": "",
        }

    def matching(
        self,
        apply_methods: list[str] | None = None,
        min_score: int = 0,
        only_unviewed: bool = False,
        only_bookmarked: bool = False,
    ) -> list[dict[str, Any]]:
        """Same rules as db._apply_pipeline_filters."""
        return [
            x
            for x in self.listings
            if x["status"] in db.PIPELINE_STATUSES
            and (not apply_methods or x["apply_method"] in apply_methods)
            and (x["score"] or 0) >= min_score
            and not (only_unviewed and x["viewed_at"])
            and not (only_bookmarked and not x["bookmarked"])
        ]

    def page(
        self, sort_by: str = "first_seen", limit: int = 20, offset: int = 0, **filters: Any
    ) -> list[dict[str, Any]]:
        rows = self.matching(**filters)
        if sort_by == "score":
            rows = sorted(rows, key=lambda x: x["score"] or 0, reverse=True)
        return rows[offset : offset + limit]

    def draft_one(self, listing: Any) -> None:
        """Stand-in for the LLM drafting: a new draft each call, like the real one."""
        n = sum(1 for w in self.writes if w[0] == "draft") + 1
        self.writes.append(("draft", listing.id))
        self.drafts[listing.id] = {
            "id": f"d{n}-{listing.id}",
            "body": f"Draft {n}: Sehr geehrte Damen und Herren",
            "adapted_cv": f"# CV draft {n}",
            "model": "fake-llm",
        }

    def set_bookmarked(self, listing_id: str, on: bool) -> None:
        self.writes.append(("star", listing_id, on))
        listing = self.by_id(listing_id)
        if listing is not None:
            listing["bookmarked"] = on

    def save_profile(self, profile: dict[str, Any]) -> None:
        self.writes.append(("profile", dict(profile)))
        self.profile = dict(profile)

    def mark_viewed(self, listing_id: str) -> None:
        self.writes.append(("viewed", listing_id))
        listing = self.by_id(listing_id)
        if listing is not None:
            listing["viewed_at"] = "2026-11-06T12:00:00+00:00"

    def by_id(self, listing_id: str) -> dict[str, Any] | None:
        return next((x for x in self.listings if x["id"] == listing_id), None)

    def set_status(self, listing_id: str, status: Any) -> None:
        self.writes.append(("status", listing_id, status.value))
        listing = self.by_id(listing_id)
        if listing is not None:
            listing["status"] = status.value


def _no_supabase() -> None:
    raise RuntimeError("UI tests run on the fake DB; nothing may reach Supabase")


def install(set_attr: Callable[[Any, str, Any], None], fake: FakeDB) -> None:
    """Point the Pipeline and Settings UI's DB calls at `fake`. `set_attr` is monkeypatch.setattr or builtin setattr."""
    set_attr(db, "_client", _no_supabase)  # anything that slips past the fakes fails loudly, never hits Supabase
    set_attr(pipeline, "count_pipeline_listings", lambda **kw: len(fake.matching(**kw)))
    set_attr(pipeline, "list_pipeline_listings", fake.page)
    set_attr(pipeline, "get_listing_by_id", fake.by_id)
    set_attr(pipeline, "mark_listing_viewed", fake.mark_viewed)
    set_attr(pipeline, "count_listings_new_today", lambda: 3)
    set_attr(pipeline, "count_submissions_today_external", lambda: 0)
    set_attr(pipeline, "count_submissions_last_7d", lambda: 0)
    set_attr(card, "get_latest_draft_for_listing", lambda lid: fake.drafts.get(lid))
    set_attr(card, "update_listing_status", fake.set_status)
    set_attr(card, "set_listing_bookmarked", fake.set_bookmarked)
    set_attr(draft, "draft_one", fake.draft_one)
    set_attr(card, "insert_apply_request", lambda listing_id, source: fake.writes.append(("apply", listing_id)))
    set_attr(
        card,
        "update_draft_content",
        lambda draft_id, body, adapted_cv: fake.writes.append(("save", draft_id, body, adapted_cv)),
    )
    set_attr(cv_render, "load_profile", lambda: dict(fake.profile))  # the real PDF renderer, fake photo source
    set_attr(settings, "load_profile", lambda: dict(fake.profile))
    set_attr(settings, "upsert_profile", fake.save_profile)
    set_attr(settings, "clear_profile_cache", lambda: None)

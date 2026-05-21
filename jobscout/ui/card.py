"""Single-listing renderer (cards + helpers).

Helpers are pure functions, unit-tested. `render()` is Streamlit-dependent
and verified via Playwright MCP smoke against scripts/manual_card_test.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import streamlit as st

from jobscout.db import (
    get_latest_draft_for_listing,
    mark_listing_viewed,
    update_listing_status,
)
from jobscout.models import ApplyMethod, Arrangement, JobType, ListingStatus


def score_pill_class(score: int | None) -> str:
    if score is None or score < 60:
        return "jobscout-score jobscout-score-low"
    if score < 80:
        return "jobscout-score jobscout-score-mid"
    return "jobscout-score jobscout-score-high"


def favicon_url(listing_url: str, company_url_direct: str | None) -> str:
    """Prefer company_url_direct's host over the job-board host. Drop the
    leftmost subdomain label (www., jobs., boards., ...) when the host has
    3+ parts so the favicon resolves to the registered domain."""
    candidate = company_url_direct or listing_url
    try:
        host = urlparse(candidate).hostname or ""
    except Exception:
        host = ""
    parts = host.split(".")
    if len(parts) >= 3:
        host = ".".join(parts[1:])
    if not host:
        host = "example.com"
    return f"https://www.google.com/s2/favicons?domain={host}&sz=32"


def short_relative_time(when: datetime | None) -> str:
    if when is None:
        return ""
    now = datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta = now - when
    seconds = int(delta.total_seconds())
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def arrangement_badge_class(arr: Arrangement | None) -> str:
    suffix = {
        Arrangement.REMOTE: "remote",
        Arrangement.HYBRID: "hybrid",
        Arrangement.ONSITE: "onsite",
        Arrangement.UNKNOWN: "unknown-arr",
    }.get(arr, "unknown-arr")
    return f"jobscout-badge jobscout-badge-{suffix}"


def job_type_badge_class(jt: JobType | None) -> str:
    if jt in (JobType.FULLTIME, JobType.PERMANENT):
        return f"jobscout-badge jobscout-badge-{jt.value}"
    return "jobscout-badge jobscout-badge-dropped"


def apply_method_badge_class(am: ApplyMethod | None) -> str:
    if am == ApplyMethod.EXTERNAL_APPLY:
        return "jobscout-badge jobscout-badge-external"
    return "jobscout-badge jobscout-badge-easy"


def _escape(s: str | None) -> str:
    if not s:
        return ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _enum(cls, value):
    if value is None:
        return None
    try:
        return cls(value)
    except (ValueError, TypeError):
        return None


def render(listing: dict[str, Any]) -> None:
    """Render one listing card with collapsed metadata + expandable detail.

    `listing` is a dict from db.list_pipeline_listings."""
    seen = listing.get("viewed_at") is not None
    score = listing.get("score")
    score_str = str(score) if score is not None else "—"

    with st.container(border=True):
        col_title, col_score = st.columns([5, 1])
        with col_title:
            seen_mark = '<span class="jobscout-seen-mark">✓</span>' if seen else ""
            raw = listing.get("raw") or {}
            favicon = favicon_url(
                listing.get("url", ""),
                raw.get("company_url_direct") if isinstance(raw, dict) else None,
            )
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px">'
                f'<img src="{favicon}" width="20" height="20" style="border-radius:4px" alt="" />'
                f'<div style="font-weight:600;font-size:15px">{seen_mark}{_escape(listing.get("title", ""))}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
        with col_score:
            st.markdown(
                f'<div class="{score_pill_class(score)}">{score_str}</div>',
                unsafe_allow_html=True,
            )

        raw = listing.get("raw") or {}
        company = (raw.get("company") if isinstance(raw, dict) else "") or ""
        location = listing.get("location") or ""
        posted_at = listing.get("posted_at")
        if isinstance(posted_at, str):
            try:
                posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
            except Exception:
                posted_at = None
        relative = short_relative_time(posted_at)
        meta_bits = [b for b in (company, location, f"posted {relative}" if relative else "") if b]
        if meta_bits:
            st.markdown(
                f'<div class="jobscout-meta">{" · ".join(_escape(b) for b in meta_bits)}</div>',
                unsafe_allow_html=True,
            )

        arr = _enum(Arrangement, listing.get("arrangement"))
        jt = _enum(JobType, listing.get("job_type_classified"))
        am = _enum(ApplyMethod, listing.get("apply_method"))
        badges_html = ""
        if arr is not None:
            badges_html += f'<span class="{arrangement_badge_class(arr)}">{arr.value}</span>'
        if jt is not None:
            badges_html += f'<span class="{job_type_badge_class(jt)}">{jt.value}</span>'
        if am is not None:
            label = "external apply" if am == ApplyMethod.EXTERNAL_APPLY else "easy apply (manual)"
            badges_html += f'<span class="{apply_method_badge_class(am)}">{label}</span>'
        if badges_html:
            st.markdown(f'<div style="margin-top:8px">{badges_html}</div>', unsafe_allow_html=True)

        with st.expander("View detail + draft", expanded=False):
            marked_key = f"marked-{listing.get('id', '')}"
            if not seen and not st.session_state.get(marked_key):
                if listing.get("id"):
                    mark_listing_viewed(listing["id"])
                st.session_state[marked_key] = True

            rationale = listing.get("score_rationale") or ""
            if rationale:
                st.markdown(
                    f'<div class="jobscout-rationale"><strong>Why this scored {score_str}</strong><br/>{_escape(rationale)}</div>',
                    unsafe_allow_html=True,
                )

            desc = listing.get("description") or ""
            if desc:
                truncated = desc[:500] + ("…" if len(desc) > 500 else "")
                st.markdown("**Listing description**")
                st.markdown(truncated)
                if len(desc) > 500:
                    with st.expander("Read full description"):
                        st.markdown(desc)

            draft = get_latest_draft_for_listing(listing["id"]) if listing.get("id") else None
            if draft:
                st.markdown("**Draft cover letter**")
                edited = st.text_area(
                    "Draft body",
                    value=draft.get("body") or "",
                    key=f"draft-{listing['id']}",
                    height=150,
                    label_visibility="collapsed",
                )
                if edited != (draft.get("body") or ""):
                    st.caption("Edited (save on apply — Phase 4)")
            else:
                st.caption("No draft generated yet — run `make draft` after scoring.")

            col_left, col_right = st.columns([3, 2])
            with col_left:
                if st.button("Skip", key=f"skip-{listing.get('id', '')}", type="secondary"):
                    if listing.get("id"):
                        update_listing_status(listing["id"], ListingStatus.REJECTED)
                        st.rerun()
            with col_right:
                if am == ApplyMethod.EXTERNAL_APPLY:
                    if st.button("Apply", key=f"apply-{listing.get('id', '')}", type="primary"):
                        st.toast("Apply pipeline runs in Phase 4 — for now copy + open the listing.", icon="ℹ️")
                else:
                    st.link_button(
                        "Open in LinkedIn ↗",
                        url=listing.get("url", "#"),
                    )

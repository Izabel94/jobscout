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
    insert_apply_request,
    mark_listing_viewed,
    set_listing_bookmarked,
    update_draft_content,
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


def _fmt_eur_k(value: Any) -> str:
    """120000 -> '120k'; 67500 -> '67.5k'. Returns '' for missing/zero."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    k = n / 1000
    return f"€{k:.0f}k" if k == int(k) else f"€{k:.1f}k"


def salary_display(listing: dict[str, Any]) -> tuple[str, str] | None:
    """Return (range_label, provenance) for the card, or None when no salary
    is known. A listing-stated rate wins over a Kununu estimate."""
    lo, hi = _fmt_eur_k(listing.get("rate_min")), _fmt_eur_k(listing.get("rate_max"))
    if (lo or hi) and (listing.get("rate_unit") == "salary"):
        return (f"{lo or '?'}-{hi or '?'}/yr", "listed")
    # Only high-confidence (company/role-matched) Kununu figures are shown;
    # regional extrapolations are stored as 'kununu_low_confidence' and hidden.
    if listing.get("salary_source") == "kununu":
        lo, hi = _fmt_eur_k(listing.get("salary_min")), _fmt_eur_k(listing.get("salary_max"))
        if lo or hi:
            return (f"≈ {lo or '?'}-{hi or '?'}/yr", "Kununu")
    return None


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
        # Sidegig 559c15c pattern: invisible marker triggers green left-border
        # on the parent card via CSS :has(). Replaces the old ✓ prefix.
        if seen:
            st.markdown('<span class="jobscout-viewed-marker"></span>', unsafe_allow_html=True)

        col_title, col_score, col_star, col_remove = st.columns([5, 1, 1, 1])
        with col_title:
            raw = listing.get("raw") or {}
            favicon = favicon_url(
                listing.get("url", ""),
                raw.get("company_url_direct") if isinstance(raw, dict) else None,
            )
            st.markdown(
                f'<div class="jobscout-card-row">'
                f'<img src="{favicon}" width="20" height="20" style="border-radius:4px" alt="" />'
                f'<div class="jobscout-card-title">{_escape(listing.get("title", ""))}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
        with col_score:
            st.markdown(
                f'<div class="{score_pill_class(score)}">{score_str}</div>',
                unsafe_allow_html=True,
            )
        with col_star:
            bookmarked = bool(listing.get("bookmarked"))
            if bookmarked:
                st.markdown('<span class="jobscout-star-on-marker"></span>', unsafe_allow_html=True)
            if st.button(
                "★" if bookmarked else "☆",
                key=f"star-{listing.get('id', '')}",
                help="Remove from favorites" if bookmarked else "Save to favorites",
            ) and listing.get("id"):
                set_listing_bookmarked(listing["id"], not bookmarked)
                st.rerun()
        with col_remove:
            # Manual fallback for listings the freshness sweep misses or that
            # are inappropriate. EXPIRED is terminal and hidden by the pipeline
            # query; the worker drops any queued apply for it.
            st.markdown('<span class="jobscout-remove-marker"></span>', unsafe_allow_html=True)
            if st.button(
                "✕ Remove",
                key=f"remove-{listing.get('id', '')}",
                help="Hide this listing (expired or not relevant).",
            ) and listing.get("id"):
                update_listing_status(listing["id"], ListingStatus.EXPIRED)
                st.toast("Listing removed")
                st.rerun()

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

        salary = salary_display(listing)
        if salary:
            range_label, provenance = salary
            st.markdown(
                f'<div class="jobscout-salary">💶 {_escape(range_label)} '
                f'<span class="jobscout-salary-src">· {_escape(provenance)}</span></div>',
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
        block_reason = listing.get("apply_block_reason")
        if block_reason:
            badges_html += '<span class="jobscout-badge jobscout-badge-blocked">⚠ login wall — apply manually</span>'
        if badges_html:
            st.markdown(badges_html, unsafe_allow_html=True)

        detail = st.expander(
            "View detail + draft",
            expanded=False,
            key=f"exp-{listing.get('id', '')}",
            on_change="rerun",
        )
        # Mark viewed only when the expander is actually OPENED. Streamlit runs
        # an expander's body on every render even while collapsed, so marking
        # inside it turned every rendered card 'viewed'. `.open` + on_change=
        # 'rerun' makes the open state observable each run.
        marked_key = f"marked-{listing.get('id', '')}"
        if detail.open and not seen and not st.session_state.get(marked_key):
            if listing.get("id"):
                mark_listing_viewed(listing["id"])
            st.session_state[marked_key] = True
            st.rerun()
        with detail:
            rationale = listing.get("score_rationale") or ""
            if rationale:
                st.markdown(
                    f'<div class="jobscout-rationale"><strong>Why this scored {score_str}</strong><br/>{_escape(rationale)}</div>',
                    unsafe_allow_html=True,
                )

            salary_note = listing.get("salary_note")
            if salary_note and listing.get("salary_source") == "kununu":
                st.caption(f"Salary basis: {salary_note}")

            desc = listing.get("description") or ""
            if desc:
                st.markdown("**Listing description**")
                st.markdown(desc)

            draft = get_latest_draft_for_listing(listing["id"]) if listing.get("id") else None
            if draft:
                st.caption(
                    f"model `{draft.get('model', '?')}` · "
                    f"created {str(draft.get('created_at', '?'))[:19].replace('T', ' ')}"
                )
                if st.button("↻ Re-draft (replaces what's shown below)", key=f"redraft-{listing['id']}"):
                    from jobscout.draft import draft_one
                    from jobscout.models import Listing

                    with st.spinner("calling LLM…"):
                        try:
                            draft_one(Listing.model_validate(listing))
                            st.success("re-drafted")
                            st.rerun()
                        except Exception as e:
                            st.error(f"re-draft failed: {e}")

                st.markdown("**Draft cover letter**")
                edited = st.text_area(
                    "Draft body",
                    value=draft.get("body") or "",
                    key=f"body-{listing['id']}-{draft['id']}",
                    height=150,
                    label_visibility="collapsed",
                )
                st.markdown("**Adapted CV (markdown)**")
                edited_cv = st.text_area(
                    "Adapted CV (markdown)",
                    value=draft.get("adapted_cv") or "",
                    key=f"cv-{listing['id']}-{draft['id']}",
                    height=300,
                    label_visibility="collapsed",
                )
                _dirty = edited != (draft.get("body") or "") or edited_cv != (draft.get("adapted_cv") or "")
                if _dirty and st.button("💾 Save edits", key=f"save-{listing['id']}-{draft['id']}"):
                    update_draft_content(draft["id"], body=edited, adapted_cv=edited_cv)
                    st.toast("Edits saved — the worker will apply with these.")
                    st.rerun()
                # Styled CV as HTML — open it and print to PDF from the browser
                # (for login-walled listings you apply to by hand).
                from jobscout.cv_render import cv_markdown_to_html

                st.download_button(
                    "⬇ CV (open & print to PDF)",
                    cv_markdown_to_html(edited_cv),
                    file_name=f"cv-{listing['id'][:8]}.html",
                    mime="text/html",
                    key=f"dl-cv-{listing['id']}",
                )
            else:
                st.caption("No draft generated yet — run `make draft` after scoring.")

            col_left, col_right = st.columns([3, 2])
            with col_left:
                if st.button("Skip", key=f"skip-{listing.get('id', '')}", type="secondary"):
                    if listing.get("id"):
                        update_listing_status(listing["id"], ListingStatus.REJECTED)
                        st.rerun()
            with col_right:
                if block_reason:
                    raw = listing.get("raw") or {}
                    apply_url = (raw.get("job_url_direct") if isinstance(raw, dict) else None) or listing.get("url", "#")
                    st.link_button("Apply manually on site ↗", url=apply_url)
                    st.caption("This site needs a login (e.g. Instaffo) — auto-fill isn't possible.")
                elif am == ApplyMethod.EXTERNAL_APPLY:
                    queued_key = f"queued-{listing.get('id', '')}"
                    if st.session_state.get(queued_key):
                        st.info(
                            "⏳ Queued — a Chrome window will open within a few minutes to fill this "
                            "application. Review it, then click Submit yourself. "
                            "(Keep your apply Chrome running.)"
                        )
                    elif st.button("Apply", key=f"apply-{listing.get('id', '')}", type="primary"):
                        if listing.get("id"):
                            insert_apply_request(
                                listing_id=listing["id"],
                                source=listing.get("source") or "",
                            )
                            st.session_state[queued_key] = True
                            st.toast(
                                "Apply queued ✅ — a Chrome window will open shortly to fill it.",
                                icon="✅",
                            )
                            st.rerun()
                else:
                    src = (listing.get("source") or "").lower()
                    label = "Open in LinkedIn ↗" if src == "linkedin" else "Open original posting ↗"
                    st.link_button(label, url=listing.get("url", "#"))

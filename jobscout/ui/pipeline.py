"""Pipeline tab — KPI hero + filter chips + paginated card list.

This file's render functions are Streamlit-dependent. Smoke tested via
Playwright MCP at the end of each phase block."""

from __future__ import annotations

import streamlit as st

from jobscout.db import (
    count_listings_in_dashboard,
    count_listings_new_today,
    count_pipeline_listings,
    count_submissions_last_7d,
    count_submissions_today_external,
    list_pipeline_listings,
)
from jobscout.ui.card import render as render_card

APPLY_DAILY_CAP = 10


def _kpi_tile(label: str, value_html: str) -> None:
    st.markdown(
        f'<div class="jobscout-kpi-tile">'
        f'<div class="jobscout-kpi-label">{label}</div>'
        f'<div class="jobscout-kpi-value">{value_html}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_kpi_hero() -> None:
    new_today = count_listings_new_today()
    applied_today = count_submissions_today_external()
    in_dashboard = count_listings_in_dashboard()
    submitted_7d = count_submissions_last_7d()
    remaining = max(0, APPLY_DAILY_CAP - applied_today)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _kpi_tile("New today", str(new_today))
    with col2:
        _kpi_tile("Auto-apply remaining",
                  f'<span>{remaining}</span><span class="jobscout-kpi-suffix"> / {APPLY_DAILY_CAP}</span>')
    with col3:
        _kpi_tile("In dashboard", str(in_dashboard))
    with col4:
        _kpi_tile("Submitted (7d)", str(submitted_7d))


_PAGE_SIZE = 20
_FILTERS = [
    ("all", "All"),
    ("unviewed", "Unviewed"),
    ("external", "External apply"),
    ("easy", "Easy apply"),
]
_SORTS = {"first_seen": "First seen (newest)", "score": "Score (highest)"}


def render_sidebar_filters() -> None:
    """Sidebar filters (sidegig pattern). Writes filter_kind + sort_by into
    session_state. Replaces the old chip-row layout that had alignment issues."""
    if "filter_kind" not in st.session_state:
        st.session_state["filter_kind"] = "all"
    if "sort_by" not in st.session_state:
        st.session_state["sort_by"] = "first_seen"
    if "page" not in st.session_state:
        st.session_state["page"] = 0

    with st.sidebar:
        st.markdown("### Pipeline filters")

        # Compute counts so labels show how many listings each filter would surface.
        counts = {key: count_pipeline_listings(filter_kind=key) for key, _ in _FILTERS}

        new_filter = st.radio(
            "Show",
            options=[key for key, _ in _FILTERS],
            format_func=lambda k: f"{dict(_FILTERS)[k]} ({counts[k]})",
            index=[key for key, _ in _FILTERS].index(st.session_state["filter_kind"]),
            key="filter-radio",
        )
        if new_filter != st.session_state["filter_kind"]:
            st.session_state["filter_kind"] = new_filter
            st.session_state["page"] = 0
            st.rerun()

        new_sort = st.selectbox(
            "Sort by",
            options=list(_SORTS.keys()),
            format_func=lambda k: _SORTS[k],
            index=list(_SORTS.keys()).index(st.session_state["sort_by"]),
            key="sort-select",
        )
        if new_sort != st.session_state["sort_by"]:
            st.session_state["sort_by"] = new_sort
            st.session_state["page"] = 0
            st.rerun()


# Back-compat shim — app.py calls render_filter_bar()
render_filter_bar = render_sidebar_filters


def render_listing_list() -> None:
    fk = st.session_state.get("filter_kind", "all")
    sb = st.session_state.get("sort_by", "first_seen")
    page = st.session_state.get("page", 0)
    offset = page * _PAGE_SIZE

    total = count_pipeline_listings(filter_kind=fk)
    listings = list_pipeline_listings(filter_kind=fk, sort_by=sb, limit=_PAGE_SIZE, offset=offset)

    if total == 0:
        render_empty_state()
        return

    for listing in listings:
        render_card(listing)

    start = offset + 1
    end = min(offset + _PAGE_SIZE, total)
    nav_cols = st.columns([2, 4, 2])
    with nav_cols[0]:
        if page > 0:
            if st.button("← Previous", key="page-prev"):
                st.session_state["page"] = page - 1
                st.rerun()
    with nav_cols[1]:
        st.markdown(
            f'<div class="jobscout-pagination-status">Showing {start}–{end} of {total}</div>',
            unsafe_allow_html=True,
        )
    with nav_cols[2]:
        if end < total:
            if st.button("Next →", key="page-next"):
                st.session_state["page"] = page + 1
                st.rerun()


def render_empty_state() -> None:
    fk = st.session_state.get("filter_kind", "all")
    if fk != "all":
        # Filter excludes everything — sidebar radio is the way to clear it.
        st.info("No listings match the current filter. Adjust the sidebar to see more.")
        return

    # No listings at all — friendly copy + last-run summary if available
    last_run = _last_source_run()
    if last_run is None:
        st.markdown(
            '<div class="jobscout-empty-callout">'
            '<div class="jobscout-empty-title">Nothing here yet</div>'
            '<div class="jobscout-empty-body">The pipeline runs daily at 10:30 Berlin time. Check back tomorrow.</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        return

    from jobscout.ui.card import short_relative_time
    ago = short_relative_time(last_run.get("started_at"))
    count = last_run.get("listings_new") or 0
    st.markdown(
        '<div class="jobscout-empty-callout">'
        '<div class="jobscout-empty-title">Nothing here yet</div>'
        f'<div class="jobscout-empty-body">Last pipeline run {ago}, surfaced {count} listings. The next run is daily at 10:30 Berlin time.</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def _last_source_run():
    """Most recent source_runs row or None."""
    try:
        from jobscout.db import _client
        r = (
            _client().table("source_runs")
            .select("started_at,listings_found,listings_new,error")
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        if r.data:
            from datetime import datetime
            row = r.data[0]
            if isinstance(row.get("started_at"), str):
                row["started_at"] = datetime.fromisoformat(row["started_at"].replace("Z", "+00:00"))
            return row
    except Exception:
        pass
    return None


def safe_render(fn):
    """Wrap a render function in try/except — show friendly error + debug disclosure."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            import traceback
            st.markdown(
                '<div class="jobscout-error-callout">'
                '<div class="jobscout-error-title">Something broke. The operator has been notified.</div>'
                "</div>",
                unsafe_allow_html=True,
            )
            with st.expander("Show error (debug)"):
                st.code(traceback.format_exc())
            try:
                from jobscout.db import _client
                _client().table("source_runs").insert({
                    "source": "ui",
                    "error": str(e)[:1000],
                }).execute()
            except Exception:
                pass
    return wrapper

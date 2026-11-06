"""Pipeline tab — KPI hero + filter chips + paginated card list.

This file's render functions are Streamlit-dependent. Smoke tested via
Playwright MCP at the end of each phase block."""

from __future__ import annotations

from typing import Any

import streamlit as st

from jobscout.db import (
    PIPELINE_STATUSES,
    count_listings_new_today,
    count_pipeline_listings,
    count_submissions_last_7d,
    count_submissions_today_external,
    get_listing_by_id,
    list_pipeline_listings,
    mark_listing_viewed,
)
from jobscout.ui.card import render_detail, render_row

APPLY_DAILY_CAP = 10


def render_kpi_hero() -> None:
    """One quiet line of counts instead of four big tiles."""
    new_today = count_listings_new_today()
    remaining = max(0, APPLY_DAILY_CAP - count_submissions_today_external())
    in_dashboard = count_pipeline_listings(**_current_filter_args())
    submitted_7d = count_submissions_last_7d()
    st.markdown(
        f'<div class="jobscout-stats"><span><b>{new_today}</b> new today</span>'
        f"<span><b>{remaining} of {APPLY_DAILY_CAP}</b> auto-applies left today</span>"
        f"<span><b>{in_dashboard}</b> in dashboard</span>"
        f"<span><b>{submitted_7d}</b> submitted this week</span></div>",
        unsafe_allow_html=True,
    )


_PAGE_SIZE = 20
_APPLY_METHOD_OPTIONS = ["external_apply", "easy_apply"]
_APPLY_METHOD_LABELS = {"external_apply": "External apply", "easy_apply": "Easy apply"}
_SORTS = {"first_seen": "First seen (newest)", "score": "Score (highest)"}


def render_sidebar_filters() -> None:
    """Sidebar filters (sidegig pattern) — multiselect apply method + score
    slider + only-unviewed checkbox + sort dropdown. All filters AND together."""
    if "apply_methods" not in st.session_state:
        st.session_state["apply_methods"] = []
    if "min_score" not in st.session_state:
        st.session_state["min_score"] = 60
    if "only_unviewed" not in st.session_state:
        st.session_state["only_unviewed"] = False
    if "only_bookmarked" not in st.session_state:
        st.session_state["only_bookmarked"] = False
    if "sort_by" not in st.session_state:
        st.session_state["sort_by"] = "first_seen"
    if "page" not in st.session_state:
        st.session_state["page"] = 0

    with st.sidebar:
        st.markdown("### Pipeline filters")

        new_methods = st.multiselect(
            "Apply method",
            options=_APPLY_METHOD_OPTIONS,
            format_func=lambda k: _APPLY_METHOD_LABELS[k],
            default=st.session_state["apply_methods"],
            key="filter-methods",
            help="Empty = both",
        )
        if new_methods != st.session_state["apply_methods"]:
            st.session_state["apply_methods"] = new_methods
            st.session_state["page"] = 0
            st.rerun()

        new_score = st.slider(
            "Min score",
            min_value=0,
            max_value=100,
            value=st.session_state["min_score"],
            step=5,
            key="filter-score",
        )
        if new_score != st.session_state["min_score"]:
            st.session_state["min_score"] = new_score
            st.session_state["page"] = 0
            st.rerun()

        new_unviewed = st.checkbox(
            "Only unviewed",
            value=st.session_state["only_unviewed"],
            key="filter-unviewed",
            help="Hide listings you've already opened.",
        )
        if new_unviewed != st.session_state["only_unviewed"]:
            st.session_state["only_unviewed"] = new_unviewed
            st.session_state["page"] = 0
            st.rerun()

        new_bookmarked = st.checkbox(
            "★ Favorites only",
            value=st.session_state["only_bookmarked"],
            key="filter-bookmarked",
            help="Show only listings you've starred.",
        )
        if new_bookmarked != st.session_state["only_bookmarked"]:
            st.session_state["only_bookmarked"] = new_bookmarked
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


def _current_filter_args() -> dict[str, Any]:
    return {
        "apply_methods": st.session_state.get("apply_methods") or None,
        "min_score": int(st.session_state.get("min_score") or 0),
        "only_unviewed": bool(st.session_state.get("only_unviewed")),
        "only_bookmarked": bool(st.session_state.get("only_bookmarked")),
    }


_SELECTED_KEY = "selected_listing_id"


def _select(listing_id: str) -> None:
    """Row click: show that job and mark it viewed (viewed = the user opened it, as before)."""
    st.session_state[_SELECTED_KEY] = listing_id
    if not st.session_state.get(f"marked-{listing_id}"):
        mark_listing_viewed(listing_id)
        st.session_state[f"marked-{listing_id}"] = True


def _clear_selection() -> None:
    st.session_state.pop(_SELECTED_KEY, None)


def _selected_listing(listings: list[dict[str, Any]], only_unviewed: bool) -> dict[str, Any] | None:
    """The clicked job, else the first one on the page.

    Under 'Only unviewed', opening a job removes it from the list; it's fetched directly so it
    doesn't jump away while you work on it. Otherwise a job that left the list is not kept,
    and neither is anything that left the pipeline (skipped, hidden, submitted...)."""
    selected_id = st.session_state.get(_SELECTED_KEY)
    if selected_id:
        for listing in listings:
            if listing.get("id") == selected_id:
                return listing
        if only_unviewed:
            fetched = get_listing_by_id(selected_id)
            if fetched and fetched.get("status") in PIPELINE_STATUSES:
                return fetched
    return listings[0] if listings else None


def _reset_selection_on_filter_change(filters: dict[str, Any], sort_by: str) -> None:
    """A new filter or sort shows a new list; start from its first job."""
    signature = repr((sorted(filters.items()), sort_by))
    if st.session_state.get("selection-filter-signature") != signature:
        st.session_state["selection-filter-signature"] = signature
        _clear_selection()


def render_listing_list() -> None:
    filters = _current_filter_args()
    sb = st.session_state.get("sort_by", "first_seen")
    page = st.session_state.get("page", 0)
    offset = page * _PAGE_SIZE

    total = count_pipeline_listings(**filters)
    listings = list_pipeline_listings(**filters, sort_by=sb, limit=_PAGE_SIZE, offset=offset)

    if total == 0:
        render_empty_state()
        return
    if not listings and page > 0:  # the last page emptied (e.g. 'Only unviewed'): step back
        st.session_state["page"] = page - 1
        st.rerun()

    _reset_selection_on_filter_change(filters, sb)
    selected = _selected_listing(listings, filters["only_unviewed"])
    col_list, col_detail = st.columns([2, 3], gap="medium")
    with col_list:
        with st.container(border=True, key="job-list"):  # height: CSS, follows the screen
            for listing in listings:
                render_row(listing, selected=listing is selected, on_select=_select)
        _render_pagination(page, offset, total)
    with col_detail, st.container(border=True, key="job-detail"):
        if selected is not None and selected.get("id"):
            render_detail(selected, on_close=_clear_selection)


def _render_pagination(page: int, offset: int, total: int) -> None:
    start = offset + 1
    end = min(offset + _PAGE_SIZE, total)
    nav_cols = st.columns([2, 4, 2], vertical_alignment="center")
    with nav_cols[0]:
        if page > 0 and st.button("← Previous", key="page-prev"):
            st.session_state["page"] = page - 1
            _clear_selection()
            st.rerun()
    with nav_cols[1]:
        st.markdown(
            f'<div class="jobscout-pagination-status">{start}-{end} of {total}</div>',
            unsafe_allow_html=True,
        )
    with nav_cols[2]:
        if end < total and st.button("Next →", key="page-next"):
            st.session_state["page"] = page + 1
            _clear_selection()
            st.rerun()


def render_empty_state() -> None:
    filters = _current_filter_args()
    any_filter_active = (
        filters["apply_methods"] or filters["min_score"] > 0 or filters["only_unviewed"] or filters["only_bookmarked"]
    )
    if any_filter_active:
        st.info("No listings match the current filters. Adjust the sidebar to see more.")
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
            _client()
            .table("source_runs")
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

                _client().table("source_runs").insert(
                    {
                        "source": "ui",
                        "error": str(e)[:1000],
                    }
                ).execute()
            except Exception:
                pass

    return wrapper

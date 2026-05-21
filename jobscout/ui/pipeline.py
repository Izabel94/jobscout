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
        f'<div style="background:white;border:1px solid #eee;border-radius:10px;padding:14px">'
        f'<div style="color:#666;font-size:11px;letter-spacing:0.05em;text-transform:uppercase">{label}</div>'
        f'<div style="font-size:28px;font-weight:700;margin-top:4px">{value_html}</div>'
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
                  f'<span>{remaining}</span><span style="color:#999;font-size:18px"> / {APPLY_DAILY_CAP}</span>')
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


def render_filter_bar() -> None:
    """Render filter chips + sort. Writes selected filter/sort into session_state."""
    if "filter_kind" not in st.session_state:
        st.session_state["filter_kind"] = "all"
    if "sort_by" not in st.session_state:
        st.session_state["sort_by"] = "first_seen"
    if "page" not in st.session_state:
        st.session_state["page"] = 0

    cols = st.columns([6, 2])
    with cols[0]:
        chip_cols = st.columns(len(_FILTERS))
        for i, (key, label) in enumerate(_FILTERS):
            with chip_cols[i]:
                count = count_pipeline_listings(filter_kind=key)
                active = st.session_state["filter_kind"] == key
                btn_label = f"{label} {count}"
                if st.button(
                    btn_label,
                    key=f"chip-{key}",
                    type="primary" if active else "secondary",
                    use_container_width=True,
                ):
                    st.session_state["filter_kind"] = key
                    st.session_state["page"] = 0
                    st.rerun()
    with cols[1]:
        new_sort = st.selectbox(
            "Sort by",
            options=list(_SORTS.keys()),
            format_func=lambda k: _SORTS[k],
            index=list(_SORTS.keys()).index(st.session_state["sort_by"]),
            key="sort-select",
            label_visibility="collapsed",
        )
        if new_sort != st.session_state["sort_by"]:
            st.session_state["sort_by"] = new_sort
            st.session_state["page"] = 0
            st.rerun()


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
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

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
            f'<div style="text-align:center;color:#666;font-size:13px;padding-top:8px">Showing {start}–{end} of {total}</div>',
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
        # Filter excludes everything — show clear-filter affordance
        st.markdown(
            '<div style="background:#fafafa;border:1px dashed #ddd;border-radius:12px;padding:24px;text-align:center;color:#666;margin-bottom:14px">'
            '<div>No matches for this filter.</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("Clear filter", key="clear-filter"):
            st.session_state["filter_kind"] = "all"
            st.session_state["page"] = 0
            st.rerun()
        return

    # No listings at all — friendly copy + last-run summary if available
    last_run = _last_source_run()
    if last_run is None:
        st.markdown(
            '<div style="background:#fafafa;border:1px dashed #ddd;border-radius:12px;padding:32px;text-align:center;color:#666">'
            '<div style="font-size:16px;font-weight:600;color:#1f2937;margin-bottom:8px">Nothing here yet</div>'
            '<div style="font-size:14px">The pipeline runs daily at 10:30 Berlin time. Check back tomorrow.</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        return

    from jobscout.ui.card import short_relative_time
    ago = short_relative_time(last_run.get("started_at"))
    count = last_run.get("listings_new") or 0
    st.markdown(
        '<div style="background:#fafafa;border:1px dashed #ddd;border-radius:12px;padding:32px;text-align:center;color:#666">'
        '<div style="font-size:16px;font-weight:600;color:#1f2937;margin-bottom:8px">Nothing here yet</div>'
        f'<div style="font-size:14px">Last pipeline run {ago}, surfaced {count} listings. The next run is daily at 10:30 Berlin time.</div>'
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
                '<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:12px;padding:16px;color:#7f1d1d">'
                '<div style="font-weight:600">Something broke. The operator has been notified.</div>'
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

"""Pipeline tab — KPI hero + filter chips + paginated card list.

This file's render functions are Streamlit-dependent. Smoke tested via
Playwright MCP at the end of each phase block."""

from __future__ import annotations

import streamlit as st

from jobscout.db import (
    count_listings_in_dashboard,
    count_listings_new_today,
    count_submissions_last_7d,
    count_submissions_today_external,
)

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

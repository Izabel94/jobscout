"""Manual Streamlit harness for Phase 3 development.
Run via `streamlit run scripts/manual_card_test.py` — used only for Playwright
MCP smoke testing during Phase 3 development. Not shipped to end user."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from jobscout.ui.styles import inject as inject_styles


def main():
    st.set_page_config(page_title="card test", layout="wide")
    inject_styles()
    from jobscout.ui.pipeline import render_filter_bar, render_kpi_hero, render_listing_list
    render_kpi_hero()
    st.title("pipeline filter + list smoke")
    render_filter_bar()
    render_listing_list()


main()

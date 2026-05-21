"""Manual Streamlit harness for the Settings tab — Playwright smoke only."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from jobscout.ui.settings import render
from jobscout.ui.styles import inject as inject_styles


def main():
    st.set_page_config(page_title="settings test", layout="wide")
    inject_styles()
    st.title("Settings tab smoke")
    render()


main()

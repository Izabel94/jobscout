"""jobscout dashboard — entry point.

Tabs: Pipeline (default), Settings. Password gate when JOBSCOUT_DEPLOYED=1.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit Cloud runs this file directly without the repo root on sys.path;
# this insert makes `from jobscout.X import Y` resolve. No-op locally.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st  # noqa: E402

from jobscout.ui import pipeline as pipeline_mod  # noqa: E402
from jobscout.ui import settings as settings_mod  # noqa: E402
from jobscout.ui.auth import auth_gate  # noqa: E402
from jobscout.ui.styles import inject as inject_styles  # noqa: E402


def main() -> None:
    st.set_page_config(page_title="jobscout", layout="wide")
    inject_styles()
    auth_gate()

    st.markdown(
        '<div style="display:flex;justify-content:space-between;align-items:center;'
        'padding-bottom:12px;border-bottom:1px solid #eee;margin-bottom:16px">'
        '<div style="font-weight:700;font-size:20px">jobscout</div></div>',
        unsafe_allow_html=True,
    )

    pipeline_tab, settings_tab = st.tabs(["Pipeline", "Settings"])
    with pipeline_tab:
        pipeline_mod.render_kpi_hero()
        pipeline_mod.render_filter_bar()
        pipeline_mod.safe_render(pipeline_mod.render_listing_list)()
    with settings_tab:
        settings_mod.render()


main()

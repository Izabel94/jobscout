"""The real jobscout app (app.py, both tabs) wired to the in-memory fake DB, for the browser e2e tests.

Run by tests/test_ui_e2e.py via `streamlit run`. Nothing here touches Supabase.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from tests.ui_fake_db import FakeDB, install, make_draft, sample_listings  # noqa: E402


@st.cache_resource
def _fake() -> FakeDB:
    fake = FakeDB(sample_listings(24))
    long_cv = "\n".join(f"- achievement {i}: shipped something measurable" for i in range(60))
    fake.drafts["l0"] = {**make_draft("l0"), "adapted_cv": f"# CV\n\n{long_cv}"}
    return fake


install(setattr, _fake())
runpy.run_path(str(_ROOT / "jobscout" / "ui" / "app.py"), run_name="__main__")

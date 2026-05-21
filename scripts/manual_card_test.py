"""Manual Streamlit harness: renders a few synthetic cards via card.render().
Run via `streamlit run scripts/manual_card_test.py` — used only for Playwright
MCP smoke testing during Phase 3 development. Not shipped to end user."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from jobscout.ui.card import render as render_card
from jobscout.ui.styles import inject as inject_styles


_FIXTURE_UUIDS = [
    "00000000-0000-0000-0000-000000000001",
    "00000000-0000-0000-0000-000000000002",
    "00000000-0000-0000-0000-000000000003",
]


def _fixture_listing(**overrides):
    base = {
        "id": _FIXTURE_UUIDS[0],
        "url": "https://www.linkedin.com/jobs/view/123",
        "title": "Senior Performance Marketing Manager",
        "description": "Drive paid media strategy across SEA, programmatic, and paid social. Own €5M annual budget.",
        "location": "Hamburg",
        "score": 87,
        "score_rationale": "Strong title match, in-house brand, Hamburg, programmatic stack aligns.",
        "arrangement": "remote",
        "job_type_classified": "fulltime",
        "apply_method": "external_apply",
        "viewed_at": None,
        "raw": {"company": "Otto GmbH", "company_url_direct": "https://www.otto.de/karriere"},
    }
    base.update(overrides)
    return base


def main():
    st.set_page_config(page_title="card test", layout="wide")
    inject_styles()
    # KPI hero (real Supabase counts) — for Playwright smoke
    from jobscout.ui.pipeline import render_kpi_hero
    render_kpi_hero()
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.title("card.render() Playwright smoke")
    render_card(_fixture_listing())
    render_card(_fixture_listing(
        id=_FIXTURE_UUIDS[1],
        title="Online Marketing Manager (m/w/d)",
        score=72,
        arrangement="hybrid",
        apply_method="easy_apply",
        viewed_at="2026-05-21T10:00:00Z",
        raw={"company": "RTL Deutschland", "company_url_direct": None},
        url="https://www.linkedin.com/jobs/view/456",
    ))
    render_card(_fixture_listing(
        id=_FIXTURE_UUIDS[2],
        title="Paid Media Specialist",
        score=58,
        arrangement="unknown",
        apply_method="easy_apply",
        raw={"company": "Smaller Co", "company_url_direct": None},
    ))


main()

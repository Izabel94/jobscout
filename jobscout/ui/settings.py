"""Settings tab — five editable cards binding to the profiles row.

Edits accumulate in st.session_state['pending_profile']; the save bar
(Task 10) flushes them via db.upsert_profile()."""

from __future__ import annotations

import streamlit as st

from jobscout.config_loader import clear_profile_cache, load_profile
from jobscout.db import upsert_profile

_MAX_SEARCH_TERMS = 5


def _load() -> dict:
    if "pending_profile" not in st.session_state:
        st.session_state["pending_profile"] = dict(load_profile())
    return st.session_state["pending_profile"]


def render_search_terms_card() -> None:
    p = _load()
    terms = list(p.get("required_skill_keywords") or [])
    with st.container(border=True):
        st.markdown(f"**Search terms**  ·  {len(terms)} / {_MAX_SEARCH_TERMS} used")
        st.caption("The role titles jobscout searches for on LinkedIn and Indeed. Up to 5.")
        if terms:
            cols = st.columns(len(terms))
            for i, term in enumerate(terms):
                with cols[i]:
                    if st.button(f"× {term}", key=f"rm-term-{i}"):
                        terms.pop(i)
                        p["required_skill_keywords"] = terms
                        st.rerun()
        new_term = st.text_input(
            "Add search term",
            key="new-term",
            placeholder="e.g. 'Growth Manager'",
            label_visibility="collapsed",
        )
        col_l, col_r = st.columns([5, 1])
        with col_r:
            if st.button("Add", key="add-term", use_container_width=True):
                t = (new_term or "").strip()
                if t and t not in terms:
                    if len(terms) >= _MAX_SEARCH_TERMS:
                        st.warning(f"Cap is {_MAX_SEARCH_TERMS}. Remove one first.")
                    else:
                        terms.append(t)
                        p["required_skill_keywords"] = terms
                        st.rerun()


def render_arrangement_card() -> None:
    p = _load()
    prefs = set(p.get("arrangement_preferences") or [])
    with st.container(border=True):
        st.markdown("**Work arrangement**")
        st.caption("Listings outside these preferences get filtered out.")
        col_r, col_h, col_o = st.columns(3)
        with col_r:
            if st.checkbox("remote", value="remote" in prefs, key="arr-remote"):
                prefs.add("remote")
            else:
                prefs.discard("remote")
        with col_h:
            if st.checkbox("hybrid", value="hybrid" in prefs, key="arr-hybrid"):
                prefs.add("hybrid")
            else:
                prefs.discard("hybrid")
        with col_o:
            if st.checkbox("on-site", value="onsite" in prefs, key="arr-onsite"):
                prefs.add("onsite")
            else:
                prefs.discard("onsite")
        p["arrangement_preferences"] = sorted(prefs)


def render_title_denylist_card() -> None:
    p = _load()
    denies = list(p.get("title_denylist") or [])
    with st.container(border=True):
        st.markdown("**Title denylist**")
        st.caption("Job titles containing any of these words get dropped. Useful for agency-flavored roles.")
        if denies:
            cols = st.columns(len(denies))
            for i, d in enumerate(denies):
                with cols[i]:
                    if st.button(f"× {d}", key=f"rm-deny-{i}"):
                        denies.pop(i)
                        p["title_denylist"] = denies
                        st.rerun()
        new_deny = st.text_input(
            "Add word",
            key="new-deny",
            placeholder="e.g. 'SAP'",
            label_visibility="collapsed",
        )
        col_l, col_r = st.columns([5, 1])
        with col_r:
            if st.button("Add", key="add-deny", use_container_width=True):
                t = (new_deny or "").strip()
                if t and t not in denies:
                    denies.append(t)
                    p["title_denylist"] = denies
                    st.rerun()


def render_scorer_notes_card() -> None:
    p = _load()
    with st.container(border=True):
        st.markdown("**Notes for the AI scorer**")
        st.caption("Free-text guidance the LLM reads when ranking listings. Keep it short.")
        new = st.text_area(
            "Scorer notes",
            value=p.get("scorer_notes") or "",
            key="notes",
            height=100,
            label_visibility="collapsed",
        )
        p["scorer_notes"] = new


def render_salary_card() -> None:
    p = _load()
    with st.container(border=True):
        st.markdown("**Minimum salary (optional)**")
        st.caption("Listings below this annual gross salary get dropped. Leave blank to skip.")
        current = p.get("target_rate_floor_eur")
        val = st.number_input(
            "€ / year",
            min_value=0,
            value=int(current) if current else 0,
            step=5000,
            format="%d",
            key="salary",
        )
        p["target_rate_floor_eur"] = val if val > 0 else None


def render_profile_snapshot() -> None:
    p = _load()
    skills = ", ".join((p.get("skills") or [])[:5])
    last = p.get("linkedin_scraped_at") or "—"
    st.markdown(
        '<div class="jobscout-profile-snapshot">'
        '<div class="jobscout-profile-snapshot-title">Your profile (read-only — re-run bootstrap to refresh)</div>'
        f'<div><strong>Name:</strong> {p.get("full_name", "—") or "—"}</div>'
        f'<div><strong>Headline:</strong> {p.get("headline", "—") or "—"}</div>'
        f'<div><strong>Location:</strong> {p.get("location", "—") or "—"}</div>'
        f'<div><strong>Skills:</strong> {skills or "—"}</div>'
        f'<div class="jobscout-profile-snapshot-footer">Last scraped: {last}</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def save_profile_changes(pending: dict) -> None:
    """Pure: upsert pending profile dict to DB + clear cache. Extracted from
    the UI for testability."""
    upsert_profile(pending)
    clear_profile_cache()


def render_save_bar() -> None:
    if "pending_profile" not in st.session_state:
        return
    pending = st.session_state["pending_profile"]
    col_l, col_r = st.columns([6, 2])
    with col_r:
        sub_l, sub_r = st.columns(2)
        with sub_l:
            if st.button("Discard", key="discard", use_container_width=True):
                st.session_state.pop("pending_profile", None)
                st.rerun()
        with sub_r:
            if st.button("Save changes", key="save", type="primary", use_container_width=True):
                save_profile_changes(pending)
                st.session_state.pop("pending_profile", None)
                st.toast("Saved.", icon="✓")
                st.rerun()


def render() -> None:
    """Orchestrate the full Settings tab — 5 cards + snapshot + save bar."""
    render_search_terms_card()
    render_arrangement_card()
    render_title_denylist_card()
    render_scorer_notes_card()
    render_salary_card()
    render_profile_snapshot()
    render_save_bar()

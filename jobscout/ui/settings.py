"""Settings tab — five editable cards binding to the profiles row.

Edits accumulate in st.session_state['pending_profile']; the save bar
(Task 10) flushes them via db.upsert_profile()."""

from __future__ import annotations

import base64
from io import BytesIO

import streamlit as st
from PIL import Image, ImageOps

from jobscout.config_loader import clear_profile_cache, load_profile
from jobscout.db import upsert_profile

_MAX_SEARCH_TERMS = 5


def _load() -> dict:
    if "pending_profile" not in st.session_state:
        st.session_state["pending_profile"] = dict(load_profile())
    return st.session_state["pending_profile"]


def _chip_editor(field: str, kind: str, placeholder: str, cap: int | None = None) -> None:
    """Chips (click to remove) + an input with Add, for a list field of the profile.

    `kind` names the widget keys (rm-<kind>-i, new-<kind>, add-<kind>); styles.py colours
    the chips by that key."""
    p = _load()
    items = list(p.get(field) or [])
    if items:
        with st.container(horizontal=True, gap="small"):
            for i, item in enumerate(items):
                if st.button(f"× {item}", key=f"rm-{kind}-{i}"):
                    items.pop(i)
                    p[field] = items
                    st.rerun()
    with st.container(horizontal=True, gap="small", vertical_alignment="bottom", key=f"add-row-{kind}"):
        new = st.text_input(f"Add {kind}", key=f"new-{kind}", placeholder=placeholder, label_visibility="collapsed")
        if st.button("Add", key=f"add-{kind}"):
            t = (new or "").strip()
            if t and t not in items:
                if cap is not None and len(items) >= cap:
                    st.warning(f"Cap is {cap}. Remove one first.")
                else:
                    items.append(t)
                    p[field] = items
                    st.rerun()


def render_search_terms_card() -> None:
    terms = _load().get("required_skill_keywords") or []
    with st.container(border=True):
        st.markdown(f"**Search terms**  ·  {len(terms)} / {_MAX_SEARCH_TERMS} used")
        st.caption("The role titles jobscout searches for on LinkedIn and Indeed. Up to 5.")
        _chip_editor("required_skill_keywords", "term", "e.g. 'Growth Manager'", cap=_MAX_SEARCH_TERMS)


def render_arrangement_card() -> None:
    p = _load()
    prefs = set(p.get("arrangement_preferences") or [])
    with st.container(border=True):
        st.markdown("**Work arrangement**")
        st.caption("Listings outside these preferences get filtered out.")
        with st.container(horizontal=True, gap="medium", vertical_alignment="center"):
            for value, label in (("remote", "remote"), ("hybrid", "hybrid"), ("onsite", "on-site")):
                if st.checkbox(label, value=value in prefs, key=f"arr-{value}"):
                    prefs.add(value)
                else:
                    prefs.discard(value)
        p["arrangement_preferences"] = sorted(prefs)


def render_title_denylist_card() -> None:
    with st.container(border=True):
        st.markdown("**Title denylist**")
        st.caption("Job titles containing any of these words get dropped. Useful for agency-flavored roles.")
        _chip_editor("title_denylist", "deny", "e.g. 'SAP'")


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


def cv_photo_b64(data: bytes) -> str:
    """Normalise an uploaded photo for the CV: upright, RGB JPEG, at most 600x800, base64."""
    im = ImageOps.exif_transpose(Image.open(BytesIO(data))).convert("RGB")
    im.thumbnail((600, 800))
    out = BytesIO()
    im.save(out, "JPEG", quality=88)
    return base64.b64encode(out.getvalue()).decode("ascii")


def _uploader_key() -> str:
    # A new key gives a fresh, empty uploader, so after "Remove photo" picking the same file
    # again is a change (the browser fires no change event for a re-picked identical file).
    return f"photo-upload-{st.session_state.get('photo-upload-generation', 0)}"


def _apply_photo_upload() -> None:
    upload = st.session_state.get(_uploader_key())
    if upload is not None:
        _load()["photo_jpeg_b64"] = cv_photo_b64(upload.getvalue())


def render_photo_card() -> None:
    p = _load()
    with st.container(border=True):
        st.markdown("**CV photo**")
        st.caption("Shown top right on every CV PDF — uploads and downloads alike.")
        with st.container(horizontal=True, gap="medium", vertical_alignment="top"):
            if p.get("photo_jpeg_b64"):
                st.markdown(
                    f'<img class="jobscout-photo" alt="CV photo" src="data:image/jpeg;base64,{p["photo_jpeg_b64"]}">',
                    unsafe_allow_html=True,
                    width="content",
                )
            else:
                st.caption("No photo yet")
            with st.container():
                # on_change runs once per new file and before the preview above is drawn,
                # so the preview is current and "Remove" isn't undone by the file left in the uploader.
                st.file_uploader(
                    "Upload photo", type=["jpg", "jpeg", "png"], key=_uploader_key(), on_change=_apply_photo_upload
                )
                if p.get("photo_jpeg_b64") and st.button("Remove photo", key="photo-remove"):
                    p["photo_jpeg_b64"] = None
                    st.session_state["photo-upload-generation"] = st.session_state.get("photo-upload-generation", 0) + 1
                    st.rerun()


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
    with st.container(horizontal=True, horizontal_alignment="right", gap="small"):
        if st.button("Discard", key="discard"):
            st.session_state.pop("pending_profile", None)
            st.rerun()
        if st.button("Save changes", key="save", type="primary"):
            save_profile_changes(pending)
            st.session_state.pop("pending_profile", None)
            st.toast("Saved.", icon="✅")
            st.rerun()


def render() -> None:
    """Orchestrate the full Settings tab: what to search (left), how to judge and present
    (right), then the save bar. The columns stack on phones."""
    search, profile = st.columns(2, gap="medium")
    with search:
        render_search_terms_card()
        render_title_denylist_card()
        render_arrangement_card()
        render_salary_card()
    with profile:
        render_scorer_notes_card()
        render_photo_card()
        render_profile_snapshot()
    render_save_bar()

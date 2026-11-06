"""Single-listing renderers (split view) + helpers.

Helpers are pure functions, unit-tested. `render_row` draws one line of the job
list, `render_detail` the selected job; both are Streamlit-dependent.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import streamlit as st

from jobscout.db import (
    get_latest_draft_for_listing,
    insert_apply_request,
    set_listing_bookmarked,
    update_draft_content,
    update_listing_status,
)
from jobscout.models import ApplyMethod, Arrangement, JobType, ListingStatus


@st.cache_data(show_spinner=False)
def _cv_pdf(cv_md: str) -> bytes:
    """Cached CV→PDF (fpdf2) so it renders once per unique CV, not every rerun."""
    from jobscout.cv_render import cv_markdown_to_pdf_bytes

    return cv_markdown_to_pdf_bytes(cv_md)


def score_pill_class(score: int | None) -> str:
    if score is None or score < 60:
        return "jobscout-score jobscout-score-low"
    if score < 80:
        return "jobscout-score jobscout-score-mid"
    return "jobscout-score jobscout-score-high"


def favicon_url(listing_url: str, company_url_direct: str | None) -> str:
    """Prefer company_url_direct's host over the job-board host. Drop the
    leftmost subdomain label (www., jobs., boards., ...) when the host has
    3+ parts so the favicon resolves to the registered domain."""
    candidate = company_url_direct or listing_url
    try:
        host = urlparse(candidate).hostname or ""
    except Exception:
        host = ""
    parts = host.split(".")
    if len(parts) >= 3:
        host = ".".join(parts[1:])
    if not host:
        host = "example.com"
    return f"https://www.google.com/s2/favicons?domain={host}&sz=32"


def short_relative_time(when: datetime | None) -> str:
    if when is None:
        return ""
    now = datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta = now - when
    seconds = int(delta.total_seconds())
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def arrangement_badge_class(arr: Arrangement | None) -> str:
    suffix = {
        Arrangement.REMOTE: "remote",
        Arrangement.HYBRID: "hybrid",
        Arrangement.ONSITE: "onsite",
        Arrangement.UNKNOWN: "unknown-arr",
    }.get(arr, "unknown-arr")
    return f"jobscout-badge jobscout-badge-{suffix}"


def job_type_badge_class(jt: JobType | None) -> str:
    if jt in (JobType.FULLTIME, JobType.PERMANENT):
        return f"jobscout-badge jobscout-badge-{jt.value}"
    return "jobscout-badge jobscout-badge-dropped"


def apply_method_badge_class(am: ApplyMethod | None) -> str:
    if am == ApplyMethod.EXTERNAL_APPLY:
        return "jobscout-badge jobscout-badge-external"
    return "jobscout-badge jobscout-badge-easy"


def _fmt_eur_k(value: Any) -> str:
    """120000 -> '120k'; 67500 -> '67.5k'. Returns '' for missing/zero."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    k = n / 1000
    return f"€{k:.0f}k" if k == int(k) else f"€{k:.1f}k"


def salary_display(listing: dict[str, Any]) -> tuple[str, str] | None:
    """Return (range_label, provenance) for the card, or None when no salary
    is known. A listing-stated rate wins over a Kununu estimate."""
    lo, hi = _fmt_eur_k(listing.get("rate_min")), _fmt_eur_k(listing.get("rate_max"))
    if (lo or hi) and (listing.get("rate_unit") == "salary"):
        return (f"{lo or '?'}-{hi or '?'}/yr", "listed")
    # Only high-confidence (company/role-matched) Kununu figures are shown;
    # regional extrapolations are stored as 'kununu_low_confidence' and hidden.
    if listing.get("salary_source") == "kununu":
        lo, hi = _fmt_eur_k(listing.get("salary_min")), _fmt_eur_k(listing.get("salary_max"))
        if lo or hi:
            return (f"≈ {lo or '?'}-{hi or '?'}/yr", "Kununu")
    return None


def _escape(s: str | None) -> str:
    if not s:
        return ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _enum(cls, value):
    if value is None:
        return None
    try:
        return cls(value)
    except (ValueError, TypeError):
        return None


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _raw(listing: dict[str, Any]) -> dict[str, Any]:
    raw = listing.get("raw")
    return raw if isinstance(raw, dict) else {}


def city(location: str | None) -> str:
    """'Hamburg, Hamburg, Germany' -> 'Hamburg'. The list row only has room for the city."""
    return (location or "").split(",")[0].strip()


def _score_tile(score: int | None, *, big: bool = False) -> str:
    size = " jobscout-score-big" if big else ""
    label = str(score) if score is not None else "-"
    return f'<span class="{score_pill_class(score)}{size}">{label}</span>'


def render_row(listing: dict[str, Any], *, selected: bool, on_select: Callable[[str], None]) -> None:
    """One compact, clickable row in the job list. The whole row is a transparent button (see styles.py)."""
    lid = listing.get("id", "")
    seen = listing.get("viewed_at") is not None
    sub = " · ".join(b for b in (_raw(listing).get("company") or "", city(listing.get("location"))) if b)
    found = short_relative_time(_parse_ts(listing.get("first_discovered_at") or listing.get("discovered_at")))
    new_dot = "" if seen else '<span class="jobscout-new-dot" title="New"></span>'
    star = '<span class="jobscout-row-star">★</span>' if listing.get("bookmarked") else ""
    title_cls = "jobscout-row-title" + ("" if seen else " jobscout-row-title-new")
    # Selection is a class, not a different key: a key change rebuilds the row and drops keyboard focus.
    row_cls = "jobscout-row" + (" jobscout-row-selected" if selected else "")
    salary = salary_display(listing)
    salary_html = f'<div class="jobscout-salary">{_escape(salary[0])}</div>' if salary else ""
    with st.container(key=f"row-{lid}"):
        st.markdown(
            f'<div class="{row_cls}">{_score_tile(listing.get("score"))}'
            f'<div class="jobscout-row-text"><div class="{title_cls}">{_escape(listing.get("title"))}</div>'
            f'<div class="jobscout-row-sub">{_escape(sub)}</div>{salary_html}</div>'
            f'<div class="jobscout-row-side"><span>{found.removesuffix(" ago")}</span>{star}{new_dot}</div></div>',
            unsafe_allow_html=True,
        )
        st.button(listing.get("title") or "Open", key=f"open-{lid}", on_click=on_select, args=(lid,), width="stretch")


def render_detail(listing: dict[str, Any], *, on_close: Callable[[], None]) -> None:
    """The selected job: header with its actions top right, then tabs, then Skip. `on_close` runs after Skip/Hide."""
    lid = listing["id"]
    draft = get_latest_draft_for_listing(lid)
    am = _enum(ApplyMethod, listing.get("apply_method"))
    block_reason = listing.get("apply_block_reason")

    with st.container(horizontal=True, gap="small", vertical_alignment="top", key="detail-top"):
        _detail_header(listing, am, block_reason)
        with st.container(
            horizontal=True,
            gap="small",
            width="content",
            horizontal_alignment="right",
            vertical_alignment="center",
            key="detail-actions",
        ):
            _detail_actions(listing, draft, am, block_reason, on_close)

    if st.session_state.get(f"queued-{lid}"):
        st.info(
            "⏳ Queued — a Chrome window will open within a few minutes to fill this "
            "application. Review it, then click Submit yourself. (Keep your apply Chrome running.)"
        )
    if block_reason:
        st.caption("This site needs a login (e.g. Instaffo), so auto-fill isn't possible. Apply on the site directly.")

    why, desc, letter, cv = st.tabs(["Why it fits", "Job description", "Cover letter", "CV"])
    with why:
        _tab_why(listing)
    with desc:
        st.markdown(listing.get("description") or "_No description stored for this listing._")
    with letter:
        _tab_cover_letter(listing, draft)
    with cv:
        _tab_cv(listing, draft)

    with st.container(horizontal=True, horizontal_alignment="right"):
        # Skip = REJECTED.
        if st.button("Skip this job", key=f"skip-{lid}", type="tertiary"):
            update_listing_status(lid, ListingStatus.REJECTED)
            on_close()
            st.rerun()


def _detail_header(listing: dict[str, Any], am: ApplyMethod | None, block_reason: str | None) -> None:
    raw = _raw(listing)
    posted = short_relative_time(_parse_ts(listing.get("posted_at")))
    source = (listing.get("source") or "").capitalize()
    meta = " · ".join(
        b
        for b in (
            raw.get("company") or "",
            listing.get("location") or "",
            f"posted {posted}" if posted else "",
            f"via {source}" if source else "",
        )
        if b
    )
    chips = []
    arr = _enum(Arrangement, listing.get("arrangement"))
    if arr is not None and arr != Arrangement.UNKNOWN:
        chips.append(f'<span class="{arrangement_badge_class(arr)}">{arr.value}</span>')
    jt = _enum(JobType, listing.get("job_type_classified"))
    if jt is not None:
        chips.append(f'<span class="{job_type_badge_class(jt)}">{jt.value}</span>')
    if am is not None:
        label = "external apply" if am == ApplyMethod.EXTERNAL_APPLY else "easy apply (manual)"
        chips.append(f'<span class="{apply_method_badge_class(am)}">{label}</span>')
    if block_reason:
        chips.append('<span class="jobscout-badge jobscout-badge-blocked">login wall</span>')
    salary = salary_display(listing)
    if salary:
        chips.append(f'<span class="jobscout-badge jobscout-badge-salary">{_escape(salary[0])} · {salary[1]}</span>')
    else:
        chips.append('<span class="jobscout-badge jobscout-badge-unknown-arr">salary not stated</span>')
    st.markdown(
        f'<div class="jobscout-detail-head">{_score_tile(listing.get("score"), big=True)}<div>'
        f'<div class="jobscout-detail-title">{_escape(listing.get("title"))}</div>'
        f'<div class="jobscout-meta">{_escape(meta)}</div>'
        f'<div class="jobscout-chips">{"".join(chips)}</div></div></div>',
        unsafe_allow_html=True,
    )


def _detail_actions(
    listing: dict[str, Any],
    draft: dict[str, Any] | None,
    am: ApplyMethod | None,
    block_reason: str | None,
    on_close: Callable[[], None],
) -> None:
    """Favorite, hide, posting link and apply: the job header's top right."""
    lid = listing["id"]
    bookmarked = bool(listing.get("bookmarked"))
    if st.button(
        "★" if bookmarked else "☆",
        key=f"star-{lid}",
        help="Remove from favorites" if bookmarked else "Save to favorites",
    ):
        set_listing_bookmarked(lid, not bookmarked)
        st.rerun()
    # Hide = EXPIRED (terminal; the worker drops any queued apply for it). Its label is visually
    # hidden by CSS (icon only) but stays the button's accessible name.
    if st.button(
        "Hide",
        icon=":material/visibility_off:",
        key=f"remove-{lid}",
        help="Hide this listing (expired or not relevant).",
    ):
        update_listing_status(lid, ListingStatus.EXPIRED)
        on_close()
        st.toast("Listing hidden")
        st.rerun()

    posting_url = _raw(listing).get("job_url_direct") or listing.get("url") or "#"
    if block_reason:
        st.link_button("Apply on site", url=posting_url, icon=":material/open_in_new:", type="primary")
    elif am == ApplyMethod.EXTERNAL_APPLY:
        st.link_button("Posting", url=listing.get("url") or "#", icon=":material/open_in_new:")
        _apply_button(listing, draft)
    else:
        label = "Open in LinkedIn" if (listing.get("source") or "").lower() == "linkedin" else "Open posting"
        st.link_button(label, url=listing.get("url") or "#", icon=":material/open_in_new:", type="primary")


def _apply_button(listing: dict[str, Any], draft: dict[str, Any] | None) -> None:
    lid = listing["id"]
    queued_key = f"queued-{lid}"
    if st.session_state.get(queued_key):
        st.button("Queued", key=f"apply-{lid}", disabled=True)
    elif not draft:
        st.button("Apply", key=f"apply-{lid}", disabled=True, help="Draft first: Apply uploads that cover letter + CV.")
    elif st.button("Apply", key=f"apply-{lid}", type="primary"):
        insert_apply_request(listing_id=lid, source=listing.get("source") or "")
        st.session_state[queued_key] = True
        st.toast("Apply queued. A Chrome window will open shortly to fill it.", icon="✅")
        st.rerun()


def _tab_why(listing: dict[str, Any]) -> None:
    rationale = listing.get("score_rationale")
    st.markdown(rationale or "_Not scored yet._")
    salary_note = listing.get("salary_note")
    if salary_note and listing.get("salary_source") == "kununu":
        st.caption(f"Salary basis: {salary_note}")


def _run_draft(listing: dict[str, Any], done_msg: str) -> None:
    from jobscout.draft import draft_one
    from jobscout.models import Listing

    with st.spinner("calling LLM…"):
        try:
            draft_one(Listing.model_validate(listing))
            st.success(done_msg)
            st.rerun()
        except Exception as e:
            st.error(f"draft failed: {e}")


def _draft_button(listing: dict[str, Any], where: str) -> None:
    # Ported from sidegig: drafting is on demand, so no LLM call is spent on listings he skips.
    if st.button("Draft cover letter & adapt CV", key=f"draft-{where}-{listing['id']}", type="primary"):
        _run_draft(listing, "drafted")


def _kept(widget_key: str) -> str:
    """Session key that outlives the text area. Streamlit drops a widget's state once it isn't
    drawn, and only the selected job's editors are drawn, so unsaved edits are copied here."""
    return f"kept-{widget_key}"


def _keep(widget_key: str) -> None:
    st.session_state[_kept(widget_key)] = st.session_state[widget_key]


def _editor(label: str, original: str, widget_key: str) -> None:
    st.text_area(
        label,
        value=st.session_state.get(_kept(widget_key), original),
        key=widget_key,
        on_change=_keep,
        args=(widget_key,),
        height="content",
        label_visibility="collapsed",
    )


def _edits(listing: dict[str, Any], draft: dict[str, Any]) -> tuple[str, str]:
    """Current text of both editors, including unsaved edits."""
    body = st.session_state.get(_kept(f"body-{listing['id']}-{draft['id']}"), draft.get("body") or "")
    cv = st.session_state.get(_kept(f"cv-{listing['id']}-{draft['id']}"), draft.get("adapted_cv") or "")
    return body, cv


def _discard_edits(widget_keys: tuple[str, ...]) -> None:
    for key in widget_keys:
        st.session_state.pop(key, None)
        st.session_state.pop(_kept(key), None)


def _save_edits_button(listing: dict[str, Any], draft: dict[str, Any], where: str) -> None:
    body, cv = _edits(listing, draft)
    if body == (draft.get("body") or "") and cv == (draft.get("adapted_cv") or ""):
        return
    if st.button("Save edits", key=f"save-{where}-{draft['id']}", type="primary"):
        update_draft_content(draft["id"], body=body, adapted_cv=cv)
        st.toast("Edits saved. The worker will apply with these.")
        st.rerun()
    keys = (f"body-{listing['id']}-{draft['id']}", f"cv-{listing['id']}-{draft['id']}")
    st.button("Discard edits", key=f"discard-{where}-{draft['id']}", on_click=_discard_edits, args=(keys,))
    st.caption("Unsaved: Apply uses the saved version.")


def _tab_cover_letter(listing: dict[str, Any], draft: dict[str, Any] | None) -> None:
    if not draft:
        st.caption("No cover letter yet. Drafting also adapts the CV.")
        _draft_button(listing, "letter")
        return
    st.caption(
        f"model `{draft.get('model', '?')}` · created {str(draft.get('created_at', '?'))[:16].replace('T', ' ')}"
    )
    _editor("Cover letter", draft.get("body") or "", f"body-{listing['id']}-{draft['id']}")
    with st.container(horizontal=True, gap="small"):
        _save_edits_button(listing, draft, "letter")
        if st.button("Draft again", key=f"redraft-{listing['id']}", help="Replaces the cover letter and CV"):
            _run_draft(listing, "re-drafted")


def _tab_cv(listing: dict[str, Any], draft: dict[str, Any] | None) -> None:
    if not draft:
        st.caption("No adapted CV yet. Drafting creates the cover letter and the CV together.")
        _draft_button(listing, "cv")
        return
    _editor("Adapted CV (markdown)", draft.get("adapted_cv") or "", f"cv-{listing['id']}-{draft['id']}")
    _, edited_cv = _edits(listing, draft)
    with st.container(horizontal=True, gap="small"):
        _save_edits_button(listing, draft, "cv")
        # Direct CV PDF (fpdf2, pure Python, renders on Cloud) for listings you apply to by hand.
        st.download_button(
            "CV as PDF",
            _cv_pdf(edited_cv),
            icon=":material/download:",
            file_name=f"cv-{listing['id'][:8]}.pdf",
            mime="application/pdf",
            key=f"dl-cv-{listing['id']}",
        )

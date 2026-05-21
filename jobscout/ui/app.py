"""Streamlit dashboard: Pipeline / Onboarding / Observability tabs."""

import os
import sys
from pathlib import Path
from typing import Any

# Streamlit Cloud runs `jobscout/ui/app.py` without the repo root on sys.path,
# so `from jobscout.db import ...` fails. Insert the root before imports.
# No-op locally — poetry's editable install already puts it on sys.path.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st  # noqa: E402

from jobscout.db import (  # noqa: E402
    get_latest_draft_for_listing,
    list_onboarding_targets,
    list_pipeline_listings_legacy,
    list_source_runs,
    record_submission,
    update_listing_status,
    update_onboarding_status,
)
from jobscout.models import ListingStatus  # noqa: E402

_JOBSCOUT_DEPLOYED = bool(os.environ.get("JOBSCOUT_DEPLOYED"))


def _auth_gate() -> None:
    """Password gate when deployed; no-op locally."""
    if not _JOBSCOUT_DEPLOYED or st.session_state.get("jobscout_authed"):
        return
    expected = os.environ.get("JOBSCOUT_PASSWORD") or st.secrets.get("JOBSCOUT_PASSWORD", "")
    if not expected:
        st.error("JOBSCOUT_PASSWORD not configured in secrets.")
        st.stop()
    st.title("jobscout")
    with st.form("auth", clear_on_submit=False):
        pw = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    # Streamlit emits autocomplete="new-password" and exposes no username field,
    # so 1Password treats the page as a set-new-password screen and refuses to
    # autofill. Override to current-password AND inject a visually-hidden
    # username field — web.dev's documented pattern for password-only logins.
    # See streamlit#3080. The username value is never read by Python.
    st.html(
        """
        <script>
        (function() {
          const SENTINEL = 'data-jobscout-uname';
          const decorate = () => {
            document.querySelectorAll('input[type="password"]').forEach(pw => {
              pw.setAttribute('autocomplete', 'current-password');
              pw.setAttribute('name', 'password');
              const host = pw.parentElement;
              if (!host || host.querySelector(`input[${SENTINEL}]`)) return;
              const u = document.createElement('input');
              u.type = 'text';
              u.name = 'username';
              u.setAttribute('autocomplete', 'username');
              u.setAttribute(SENTINEL, 'true');
              u.setAttribute('aria-hidden', 'true');
              u.tabIndex = -1;
              u.style.cssText = 'position:absolute;left:-9999px;width:1px;height:1px;opacity:0;pointer-events:none;';
              host.insertBefore(u, pw);
            });
          };
          decorate();
          const observer = new MutationObserver(decorate);
          observer.observe(document.body, { childList: true, subtree: true });
          setTimeout(() => observer.disconnect(), 5000);
        })();
        </script>
        """,
        unsafe_allow_javascript=True,
    )
    if submitted:
        if pw == expected:
            st.session_state["jobscout_authed"] = True
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()


_DEFAULT_UPWORK_CDP_URL = "http://localhost:9222"


@st.cache_data(ttl=5)
def _cdp_chrome_running(cdp_url: str) -> bool:
    """True if a Chrome instance is reachable at the CDP URL.

    Probes `/json/version` (Chrome's DevTools handshake endpoint). 5s cache
    so the button doesn't re-probe on every Streamlit rerun, but a freshly
    launched Chrome shows up within a few seconds.
    """
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(cdp_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 9222
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False

_SUBMISSION_CHANNELS = ["upwork_ui", "linkedin_ea", "freelancermap_form", "bundesagentur", "email"]
_STATUS_OPTIONS = ["scored", "drafted", "copied", "submitted"]
_ONBOARDING_STATUSES = ["not_started", "in_progress", "applied", "accepted", "rejected", "dormant"]
_SOURCE_LABELS = {
    "upwork": "Upwork",
    "linkedin": "LinkedIn",
    "bundesagentur": "Bundesagentur",
    "freelancermap": "freelancermap",
}

st.set_page_config(page_title="jobscout", layout="wide", initial_sidebar_state="expanded")
_auth_gate()

# ── Custom styling ───────────────────────────────────────────────────────
st.markdown(
    """
    <style>
      /* Tighter top padding so the metrics sit higher */
      .block-container { padding-top: 2.5rem; padding-bottom: 4rem; }

      /* Score badge — colored pill */
      .score-badge {
        display: inline-block;
        font-weight: 700;
        font-size: 14px;
        line-height: 1;
        padding: 6px 10px;
        border-radius: 999px;
        min-width: 36px;
        text-align: center;
        color: white;
      }
      .score-badge.high { background: #16a34a; }   /* >=70 */
      .score-badge.mid  { background: #64748b; }   /* 50-69 */
      .score-badge.low  { background: #94a3b8; }   /* <50 */

      /* Source pill — subtle chip */
      .source-pill {
        display: inline-block;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        padding: 3px 9px;
        border-radius: 4px;
        background: #f1f5f9;
        color: #334155;
        border: 1px solid #e2e8f0;
      }

      /* Status chip in the row header */
      .status-chip {
        display: inline-block;
        font-size: 11px;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 999px;
        margin-left: 6px;
      }
      .status-chip.scored      { background: #dbeafe; color: #1d4ed8; }
      .status-chip.drafted     { background: #fef3c7; color: #92400e; }
      .status-chip.copied      { background: #ede9fe; color: #6d28d9; }
      .status-chip.submitted   { background: #dcfce7; color: #166534; }
      .status-chip.rejected    { background: #fee2e2; color: #991b1b; }
      /* onboarding statuses */
      .status-chip.not_started { background: #f1f5f9; color: #475569; }
      .status-chip.in_progress { background: #fef3c7; color: #92400e; }
      .status-chip.applied     { background: #dbeafe; color: #1d4ed8; }
      .status-chip.accepted    { background: #dcfce7; color: #166534; }
      .status-chip.dormant     { background: #e2e8f0; color: #475569; }

      /* Row meta line — small caption */
      .row-meta {
        color: #64748b;
        font-size: 12.5px;
        margin-top: 4px;
      }
      .row-meta a { color: #2563eb; text-decoration: none; }

      /* Rationale callout */
      .rationale {
        background: #f8fafc;
        border-left: 3px solid #94a3b8;
        padding: 8px 12px;
        margin: 6px 0 10px;
        font-size: 13.5px;
        color: #334155;
        border-radius: 0 4px 4px 0;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def _score_class(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 50:
        return "mid"
    return "low"


def _rate_summary(row: dict[str, Any]) -> str:
    """Compact one-liner for the rate cell. Returns '—' if no usable rate info."""
    lo = row.get("rate_min")
    hi = row.get("rate_max")
    currency = row.get("currency") or ""
    unit = row.get("rate_unit") or ""
    if not lo and not hi:
        return "—"
    if lo and hi and lo != hi:
        return f"{lo}–{hi} {currency} / {unit}".strip()  # noqa: RUF001
    return f"{lo or hi} {currency} / {unit}".strip()


tab_pipeline, tab_onboarding, tab_observability = st.tabs(["Pipeline", "Onboarding", "Observability"])

# ═══════════════════════════════════════════════════════════════════════════
#  PIPELINE
# ═══════════════════════════════════════════════════════════════════════════
with tab_pipeline:
    # Pre-fetch the apply queue once per render so:
    #   1. The per-row "already queued" check below is O(1) instead of one
    #      Supabase call per row.
    #   2. The sidebar queue panel can reuse the same rows.
    # The 200-row ceiling is a soft cap; if you ever have >200 active rows
    # something is very wrong with the worker. Adjust if needed.
    from jobscout.db import list_apply_requests as _list_apply_requests

    _apply_queue_rows: list[dict[str, Any]] = _list_apply_requests(limit=200)
    _active_apply_listing_ids: set[str] = {
        r["listing_id"]
        for r in _apply_queue_rows
        if r["status"] in ("pending", "processing")
    }

    # Sidebar filters
    with st.sidebar:
        st.markdown("### Pipeline filters")
        st.caption("Affect the Pipeline tab only. Empty = show everything.")
        status_filter = st.multiselect(
            "Status",
            _STATUS_OPTIONS,
            default=[],
            help="Empty = all statuses (scored, drafted, copied, submitted)",
        )
        sources_pick = st.multiselect(
            "Source",
            sorted(_SOURCE_LABELS.keys()),
            format_func=lambda s: _SOURCE_LABELS.get(s, s),
            default=[],
            help="Empty = all sources",
        )
        min_score = st.slider("Min score", min_value=0, max_value=100, value=0, step=5)
        sort_by = st.selectbox("Sort by", ["score (high → low)", "score (low → high)", "discovered (newest)"])

        # Apply queue panel — shows the 10 most recent queue rows with
        # status + any error tail. Reads from `_apply_queue_rows` above
        # (one prefetch covers both this panel and the per-row already-
        # queued check).
        st.markdown("### Apply queue")
        if not _apply_queue_rows:
            st.caption("Queue empty.")
        else:
            for _q in _apply_queue_rows[:10]:
                _status_icon = {
                    "pending": "🕐",
                    "processing": "⚙️",
                    "done": "✅",
                    "failed": "❌",
                }.get(_q["status"], "•")
                _short_id = _q["listing_id"][:8]
                _line = f"{_status_icon} `{_short_id}` {_q['source']} — {_q['status']}"
                st.caption(_line)
                if _q.get("error"):
                    st.caption(f"   ↳ {_q['error'][:120]}")
                if _q["status"] in ("failed", "done") and st.button(
                    "Re-queue",
                    key=f"requeue-{_q['id']}",
                    help="Insert a fresh apply_request for this listing. The worker picks it up within 5 min.",
                ):
                    from jobscout.db import insert_apply_request

                    try:
                        insert_apply_request(
                            listing_id=_q["listing_id"], source=_q["source"]
                        )
                        st.toast(f"Re-queued `{_short_id}` — worker will pick it up.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Re-queue failed: {e}")
                if _q["status"] in ("pending", "processing") and st.button(
                    "Cancel",
                    key=f"cancel-{_q['id']}",
                    help=(
                        "Pending: marks failed before the worker claims it. "
                        "Processing: marks failed in the DB — the local worker "
                        "may still be mid-flight, close its apply tab in CDP "
                        "Chrome to fully release."
                    ),
                ):
                    from jobscout.db import mark_apply_request_failed

                    _note = (
                        "cancelled by user before worker pickup"
                        if _q["status"] == "pending"
                        else "cancelled by user while processing — worker may still be mid-flight"
                    )
                    try:
                        mark_apply_request_failed(_q["id"], error=_note)
                        st.toast(f"Cancelled `{_short_id}`.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Cancel failed: {e}")

    # Empty status filter → show every pipeline state.
    statuses = [ListingStatus(s) for s in (status_filter or _STATUS_OPTIONS)]
    rows = list_pipeline_listings_legacy(statuses, limit=200)
    if sources_pick:
        rows = [r for r in rows if r.get("source") in sources_pick]
    rows = [r for r in rows if (r.get("score") or 0) >= min_score]
    if sort_by == "score (low → high)":
        rows.sort(key=lambda r: r.get("score") or 0)
    elif sort_by == "discovered (newest)":
        rows.sort(key=lambda r: r.get("discovered_at") or "", reverse=True)
    else:
        rows.sort(key=lambda r: r.get("score") or 0, reverse=True)

    # Hero metrics — one quick count per status that's currently filtered
    counts = {s: 0 for s in _STATUS_OPTIONS}
    for r in rows:
        counts[r.get("status", "")] = counts.get(r.get("status", ""), 0) + 1
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total visible", len(rows))
    m2.metric("Scored", counts.get("scored", 0))
    m3.metric("Drafted", counts.get("drafted", 0))
    m4.metric("Copied", counts.get("copied", 0))
    m5.metric("Submitted", counts.get("submitted", 0))

    st.divider()

    if not rows:
        st.info("No listings match the current filters. Run `make discover && make filter && make score` or relax filters.")

    for row in rows:
        score = row.get("score") or 0
        status = row.get("status", "")
        source = row.get("source", "")
        title = (row.get("title") or "(untitled)").strip()
        rate = _rate_summary(row)
        language = (row.get("language") or "").upper()
        score_cls = _score_class(score)

        with st.container(border=True):
            head_cols = st.columns([0.8, 9, 2.5])

            with head_cols[0]:
                st.markdown(
                    f'<span class="score-badge {score_cls}">{score}</span>',
                    unsafe_allow_html=True,
                )
            with head_cols[1]:
                st.markdown(
                    (
                        f'<span class="source-pill">{_SOURCE_LABELS.get(source, source)}</span> '
                        f'<span class="status-chip {status}">{status}</span><br/>'
                        f"<strong style='font-size:15px;'>{title}</strong>"
                        f'<div class="row-meta">'
                        f'<a href="{row.get("url", "#")}" target="_blank">open listing ↗</a>'
                        f"  ·  rate {rate}"
                        + (f"  ·  {language}" if language else "")
                        + "</div>"
                    ),
                    unsafe_allow_html=True,
                )
            with head_cols[2]:
                st.markdown("&nbsp;", unsafe_allow_html=True)

            with st.expander("Details, draft, and actions", expanded=False):
                if row.get("score_rationale"):
                    st.markdown(
                        f'<div class="rationale"><strong>Why this score:</strong> {row["score_rationale"]}</div>',
                        unsafe_allow_html=True,
                    )

                st.markdown("**Description**")
                st.write(row.get("description") or "_(no description)_")

                if status == "scored" and st.button(
                    "Draft proposal & adapt CV", key=f"draft-{row['id']}", type="primary"
                ):
                    from jobscout.draft import draft_one
                    from jobscout.models import Listing

                    with st.spinner("calling LLM…"):
                        try:
                            draft_one(Listing.model_validate(row))
                            st.success("drafted")
                            st.rerun()
                        except Exception as e:
                            st.error(f"draft failed: {e}")

                if status in ("drafted", "copied", "submitted"):
                    draft = get_latest_draft_for_listing(str(row["id"]))
                    if draft:
                        meta_bits = [
                            f"model `{draft.get('model', '?')}`",
                            f"created {draft.get('created_at', '?')[:19].replace('T', ' ')}",
                        ]
                        st.caption(" · ".join(meta_bits))
                        if st.button(
                            "↻ Re-draft (replaces what's shown below)",
                            key=f"redraft-{row['id']}",
                        ):
                            from jobscout.draft import draft_one
                            from jobscout.models import Listing

                            with st.spinner("calling LLM…"):
                                try:
                                    draft_one(Listing.model_validate(row))
                                    st.success("re-drafted")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"re-draft failed: {e}")

                        # Key includes the draft id so re-drafts reset the widget
                        # to the new proposal text (otherwise Streamlit's session
                        # state caches the previous body under the row-keyed widget).
                        edited_body = st.text_area(
                            "Proposal",
                            draft["body"],
                            height=220,
                            key=f"body-{row['id']}-{draft['id']}",
                        )
                        st.markdown("**Adapted CV (markdown)**")
                        st.code(draft.get("adapted_cv") or "", language="markdown")

                        # Primary action: one-click "Open & ready" — copies proposal,
                        # exports the CV PDF, opens the listing URL in the default browser,
                        # and flips the listing to `copied`. After that, the secondary
                        # actions row lets you fine-tune (copy again, re-export, mark submitted).
                        if not _JOBSCOUT_DEPLOYED and st.button(
                            "🚀 Open & ready  —  copy + export PDF + open listing",
                            key=f"openready-{row['id']}",
                            type="primary",
                            help="Copies the proposal to your clipboard, exports the CV PDF "
                            "to Downloads, opens the listing URL in your default browser, and "
                            "flips this listing to `copied`.",
                        ):
                            import webbrowser

                            import pyperclip

                            from jobscout.cv_render import cv_markdown_to_pdf

                            try:
                                pyperclip.copy(edited_body)
                                draft_short = str(draft["id"])[:8]
                                pdf_path = (
                                    Path.home()
                                    / "Downloads"
                                    / f"izabel-cv-{row['id'][:8]}-{draft_short}.pdf"
                                )
                                cv_markdown_to_pdf(draft.get("adapted_cv") or "", pdf_path)
                                webbrowser.open(row["url"])
                                update_listing_status(str(row["id"]), ListingStatus.COPIED)
                                st.toast(f"Proposal copied · PDF at {pdf_path.name} · listing opened")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Open & ready failed: {e}")

                        # Tier 3: freelancermap auto-fill — spawns the apply module
                        # in a detached subprocess so the headed browser opens
                        # alongside Streamlit. Guarded by a daily cap so volume
                        # stays human-looking. Profile must already be set up on
                        # freelancermap and the user logged into the persistent
                        # Playwright profile (first run prompts for login).
                        if not _JOBSCOUT_DEPLOYED and row.get("source") == "freelancermap":
                            from jobscout.apply import submissions_today
                            from jobscout.config_loader import load_profile

                            cap = (load_profile().get("apply_daily_caps") or {}).get("freelancermap", 5)
                            today_count = submissions_today("freelancermap")
                            remaining = max(0, cap - today_count)
                            disabled = remaining == 0
                            label = (
                                f"🤖 Auto-fill on freelancermap  ·  {remaining}/{cap} left today"
                            )
                            if st.button(
                                label,
                                key=f"autofill-fm-{row['id']}",
                                disabled=disabled,
                                help=(
                                    "Opens the listing in a Playwright window, fills the "
                                    "application form with this proposal, pauses at Submit "
                                    "for your review. First run prompts you to log into "
                                    "freelancermap once; cookies persist."
                                    if not disabled
                                    else f"Daily cap of {cap} reached — try tomorrow."
                                ),
                            ):
                                import subprocess
                                import tempfile

                                # Write proposal to a temp file so the subprocess can read
                                # it without us shoving multi-KB args through the shell.
                                with tempfile.NamedTemporaryFile(
                                    mode="w",
                                    encoding="utf-8",
                                    suffix=".txt",
                                    delete=False,
                                ) as tmp:
                                    tmp.write(edited_body)
                                    proposal_path = tmp.name
                                # Render the adapted CV to PDF NOW (Streamlit has WeasyPrint
                                # native deps via the DYLD env that make-target sets). Pass
                                # the path to the subprocess so it can attach to the apply form.
                                cv_pdf_path: Path | None = None
                                try:
                                    from jobscout.cv_render import cv_markdown_to_pdf

                                    draft_short = str(draft["id"])[:8]
                                    cv_pdf_path = (
                                        Path.home()
                                        / "Downloads"
                                        / f"izabel-cv-{row['id'][:8]}-{draft_short}.pdf"
                                    )
                                    cv_markdown_to_pdf(draft.get("adapted_cv") or "", cv_pdf_path)
                                except Exception as e:
                                    st.warning(f"CV PDF render failed (apply will skip attachment): {e}")
                                    cv_pdf_path = None

                                log_dir = Path.home() / ".cache" / "jobscout" / "apply-logs"
                                log_dir.mkdir(parents=True, exist_ok=True)
                                log_path = log_dir / f"freelancermap-{row['id'][:8]}.log"
                                try:
                                    cmd = [
                                        "poetry",
                                        "run",
                                        "python",
                                        "-m",
                                        "jobscout.apply.freelancermap",
                                        "--url",
                                        row["url"],
                                        "--proposal-file",
                                        proposal_path,
                                    ]
                                    if cv_pdf_path is not None:
                                        cmd += ["--cv-pdf-file", str(cv_pdf_path)]
                                    subprocess.Popen(
                                        cmd,
                                        stdout=log_path.open("w"),
                                        stderr=subprocess.STDOUT,
                                        start_new_session=True,
                                    )
                                    st.toast(
                                        "Auto-fill launched — check the new browser window. "
                                        f"Log: {log_path}"
                                    )
                                except Exception as e:
                                    st.error(f"Auto-fill launch failed: {e}")

                        # Tier 3: Upwork auto-fill via CDP-attached Chrome.
                        # Different launch contract than freelancermap — Playwright
                        # Chromium can't pass Cloudflare Turnstile, so we attach
                        # to the user's real Chrome (started by
                        # `bash scripts/chrome-cdp.sh`) via UPWORK_CDP_URL.
                        if not _JOBSCOUT_DEPLOYED and row.get("source") == "upwork":
                            import os

                            from jobscout.apply import submissions_today
                            from jobscout.config_loader import load_profile

                            cap = (load_profile().get("apply_daily_caps") or {}).get("upwork", 5)
                            today_count = submissions_today("upwork")
                            remaining = max(0, cap - today_count)
                            cdp_url = os.environ.get("UPWORK_CDP_URL", _DEFAULT_UPWORK_CDP_URL)
                            chrome_up = _cdp_chrome_running(cdp_url)
                            disabled = remaining == 0 or not chrome_up
                            if not chrome_up:
                                label = "🤖 Auto-fill on Upwork  ·  CDP Chrome not running"
                                tooltip = (
                                    f"Probed {cdp_url}/json/version — no Chrome answering. "
                                    "Start it with `bash scripts/chrome-cdp.sh` and the button "
                                    "will enable within a few seconds."
                                )
                            elif remaining == 0:
                                label = f"🤖 Auto-fill on Upwork  ·  0/{cap} left today"
                                tooltip = f"Daily cap of {cap} reached — try tomorrow."
                            else:
                                label = f"🤖 Auto-fill on Upwork  ·  {remaining}/{cap} left today"
                                tooltip = (
                                    "Opens the listing in your CDP-attached Chrome, types "
                                    "the proposal at ~70wpm into the cover-letter field, "
                                    "attaches the CV PDF, then pauses for you to click "
                                    "'Submit a Proposal' yourself."
                                )
                            if st.button(
                                label,
                                key=f"autofill-up-{row['id']}",
                                disabled=disabled,
                                help=tooltip,
                            ):
                                import subprocess
                                import tempfile

                                with tempfile.NamedTemporaryFile(
                                    mode="w",
                                    encoding="utf-8",
                                    suffix=".txt",
                                    delete=False,
                                ) as tmp:
                                    tmp.write(edited_body)
                                    proposal_path = tmp.name
                                # Listing description + adapted CV markdown give
                                # the LLM the context it needs to draft tailored
                                # answers to per-listing screener questions.
                                with tempfile.NamedTemporaryFile(
                                    mode="w",
                                    encoding="utf-8",
                                    suffix=".txt",
                                    delete=False,
                                ) as tmp:
                                    tmp.write(row.get("description") or "")
                                    desc_path = tmp.name
                                with tempfile.NamedTemporaryFile(
                                    mode="w",
                                    encoding="utf-8",
                                    suffix=".md",
                                    delete=False,
                                ) as tmp:
                                    tmp.write(draft.get("adapted_cv") or "")
                                    cv_md_path = tmp.name
                                cv_pdf_path: Path | None = None
                                try:
                                    from jobscout.cv_render import cv_markdown_to_pdf

                                    draft_short = str(draft["id"])[:8]
                                    cv_pdf_path = (
                                        Path.home()
                                        / "Downloads"
                                        / f"izabel-cv-{row['id'][:8]}-{draft_short}.pdf"
                                    )
                                    cv_markdown_to_pdf(draft.get("adapted_cv") or "", cv_pdf_path)
                                except Exception as e:
                                    st.warning(f"CV PDF render failed (apply will skip attachment): {e}")
                                    cv_pdf_path = None

                                log_dir = Path.home() / ".cache" / "jobscout" / "apply-logs"
                                log_dir.mkdir(parents=True, exist_ok=True)
                                log_path = log_dir / f"upwork-{row['id'][:8]}.log"
                                try:
                                    cmd = [
                                        "poetry",
                                        "run",
                                        "python",
                                        "-m",
                                        "jobscout.apply.upwork",
                                        "--url",
                                        row["url"],
                                        "--proposal-file",
                                        proposal_path,
                                        "--listing-title",
                                        row.get("title") or "",
                                        "--listing-desc-file",
                                        desc_path,
                                        "--cv-md-file",
                                        cv_md_path,
                                    ]
                                    if cv_pdf_path is not None:
                                        cmd += ["--cv-pdf-file", str(cv_pdf_path)]
                                    # Pass the resolved CDP URL explicitly so the
                                    # subprocess doesn't depend on Streamlit being
                                    # launched with UPWORK_CDP_URL in its env.
                                    env = {**os.environ, "UPWORK_CDP_URL": cdp_url}
                                    subprocess.Popen(
                                        cmd,
                                        stdout=log_path.open("w"),
                                        stderr=subprocess.STDOUT,
                                        start_new_session=True,
                                        env=env,
                                    )
                                    st.toast(
                                        "Upwork auto-fill launched — check your CDP Chrome window. "
                                        f"Log: {log_path}"
                                    )
                                except Exception as e:
                                    st.error(f"Auto-fill launch failed: {e}")

                        # Tier 3: Generic external-ATS auto-fill — used for
                        # LinkedIn external-apply links and Bundesagentur
                        # externeUrl redirects. Walks any "Jetzt bewerben" /
                        # "Apply now" hops, dismisses cookie consent, enumerates
                        # form fields, LLM-maps them, fills them. Pauses at
                        # Submit for the user to review.
                        if not _JOBSCOUT_DEPLOYED and row.get("source") in ("linkedin", "bundesagentur"):
                            import os

                            from jobscout.apply import submissions_today
                            from jobscout.config_loader import load_profile

                            src = row["source"]
                            cap = (load_profile().get("apply_daily_caps") or {}).get(src, 5)
                            today_count = submissions_today(src)
                            remaining = max(0, cap - today_count)
                            cdp_url = os.environ.get("UPWORK_CDP_URL", _DEFAULT_UPWORK_CDP_URL)
                            chrome_up = _cdp_chrome_running(cdp_url)
                            # For Bundesagentur use externeUrl when present (the
                            # listing's own URL points at arbeitsagentur.de which
                            # is a description page, not a form). LinkedIn always
                            # uses the listing URL — the script clicks Apply itself.
                            ats_url = (row.get("raw") or {}).get("externeUrl") or row["url"]
                            disabled = remaining == 0 or not chrome_up
                            if not chrome_up:
                                label = "🤖 Auto-fill on external site  ·  CDP Chrome not running"
                                tooltip = (
                                    f"Probed {cdp_url}/json/version — no Chrome answering. "
                                    "Start it with `bash scripts/chrome-cdp.sh` and the button "
                                    "will enable within a few seconds."
                                )
                            elif remaining == 0:
                                label = f"🤖 Auto-fill on external site  ·  0/{cap} left today"
                                tooltip = f"Daily cap of {cap} reached — try tomorrow."
                            else:
                                label = f"🤖 Auto-fill on external site  ·  {remaining}/{cap} left today"
                                tooltip = (
                                    "Opens the listing in your CDP-attached Chrome, walks any "
                                    "'Apply now' hops, dismisses cookie consent, and fills the "
                                    "form. Pauses for you to click Submit yourself."
                                )
                            if st.button(
                                label,
                                key=f"autofill-ext-{row['id']}",
                                disabled=disabled,
                                help=tooltip,
                            ):
                                import subprocess
                                import tempfile

                                with tempfile.NamedTemporaryFile(
                                    mode="w", encoding="utf-8", suffix=".txt", delete=False,
                                ) as tmp:
                                    tmp.write(edited_body)
                                    proposal_path = tmp.name
                                with tempfile.NamedTemporaryFile(
                                    mode="w", encoding="utf-8", suffix=".txt", delete=False,
                                ) as tmp:
                                    tmp.write(row.get("description") or "")
                                    desc_path = tmp.name
                                with tempfile.NamedTemporaryFile(
                                    mode="w", encoding="utf-8", suffix=".md", delete=False,
                                ) as tmp:
                                    tmp.write(draft.get("adapted_cv") or "")
                                    cv_md_path = tmp.name
                                ext_cv_pdf_path: Path | None = None
                                try:
                                    from jobscout.cv_render import cv_markdown_to_pdf

                                    draft_short = str(draft["id"])[:8]
                                    ext_cv_pdf_path = (
                                        Path.home()
                                        / "Downloads"
                                        / f"izabel-cv-{row['id'][:8]}-{draft_short}.pdf"
                                    )
                                    cv_markdown_to_pdf(draft.get("adapted_cv") or "", ext_cv_pdf_path)
                                except Exception as e:
                                    st.warning(f"CV PDF render failed (apply will skip attachment): {e}")
                                    ext_cv_pdf_path = None

                                log_dir = Path.home() / ".cache" / "jobscout" / "apply-logs"
                                log_dir.mkdir(parents=True, exist_ok=True)
                                log_path = log_dir / f"external-{src}-{row['id'][:8]}.log"
                                try:
                                    cmd = [
                                        "poetry",
                                        "run",
                                        "python",
                                        "-m",
                                        "jobscout.apply.external_ats",
                                        "--ats-url",
                                        ats_url,
                                        "--proposal-file",
                                        proposal_path,
                                        "--cv-md-file",
                                        cv_md_path,
                                        "--listing-title",
                                        row.get("title") or "",
                                        "--listing-desc-file",
                                        desc_path,
                                    ]
                                    if ext_cv_pdf_path is not None:
                                        cmd += ["--cv-pdf-file", str(ext_cv_pdf_path)]
                                    env = {**os.environ, "UPWORK_CDP_URL": cdp_url}
                                    subprocess.Popen(
                                        cmd,
                                        stdout=log_path.open("w"),
                                        stderr=subprocess.STDOUT,
                                        start_new_session=True,
                                        env=env,
                                    )
                                    st.toast(
                                        "External auto-fill launched — check your CDP Chrome window. "
                                        f"Log: {log_path}"
                                    )
                                except Exception as e:
                                    st.error(f"Auto-fill launch failed: {e}")

                        # Deployed mode: replace all three subprocess-spawning auto-fill
                        # buttons with a single "Queue auto-apply on Mac" button. Inserts
                        # an apply_requests row; the local launchd worker picks it up
                        # within 5 min.
                        if _JOBSCOUT_DEPLOYED and row.get("source") in (
                            "upwork", "freelancermap", "bundesagentur", "linkedin"
                        ):
                            from jobscout.db import insert_apply_request

                            already_queued = row["id"] in _active_apply_listing_ids

                            if st.button(
                                ("⏳ Already queued — your Mac will pick it up within 5 min"
                                 if already_queued else "🤖 Queue auto-apply on Mac"),
                                key=f"queue-apply-{row['id']}",
                                disabled=already_queued,
                                type=("secondary" if already_queued else "primary"),
                                help=(
                                    "Inserts a request into the apply queue. The launchd "
                                    "worker on your Mac runs every 5 minutes — it picks up "
                                    "the request, fills the form, and pauses at Submit for "
                                    "you to click."
                                ),
                            ):
                                try:
                                    insert_apply_request(listing_id=row["id"], source=row["source"])
                                    st.toast("Queued — your Mac will pick this up within 5 minutes.")
                                    st.rerun()
                                except Exception as e:
                                    import traceback
                                    # Log the full stack to stderr so the launchd-hosted
                                    # Streamlit log captures it; user sees just the message.
                                    traceback.print_exc()
                                    st.error(f"Queue insert failed: {e}")

                        st.caption("Or do steps individually:")
                        col_copy, col_pdf, col_submit = st.columns(3)
                        with col_copy:
                            if st.button("Copy proposal", key=f"copy-{row['id']}"):
                                import pyperclip

                                pyperclip.copy(edited_body)
                                update_listing_status(str(row["id"]), ListingStatus.COPIED)
                                st.toast("Copied; open the job URL")
                        with col_pdf:
                            if not _JOBSCOUT_DEPLOYED and st.button("Export CV PDF", key=f"pdf-{row['id']}"):
                                try:
                                    from jobscout.cv_render import cv_markdown_to_pdf

                                    draft_short = str(draft["id"])[:8]
                                    out = (
                                        Path.home()
                                        / "Downloads"
                                        / f"izabel-cv-{row['id'][:8]}-{draft_short}.pdf"
                                    )
                                    cv_markdown_to_pdf(draft.get("adapted_cv") or "", out)
                                    st.toast(f"Saved {out}")
                                except Exception as e:
                                    st.error(f"PDF export failed: {e}")
                        with col_submit:
                            channel = st.selectbox(
                                "Channel",
                                _SUBMISSION_CHANNELS,
                                key=f"channel-{row['id']}",
                            )
                            if st.button("Mark submitted", key=f"sub-{row['id']}"):
                                record_submission(str(row["id"]), draft["id"], channel)
                                update_listing_status(str(row["id"]), ListingStatus.SUBMITTED)
                                st.rerun()

# ═══════════════════════════════════════════════════════════════════════════
#  ONBOARDING
# ═══════════════════════════════════════════════════════════════════════════
with tab_onboarding:
    cards = list_onboarding_targets()
    status_counts: dict[str, int] = {}
    for c in cards:
        s = c.get("status", "not_started")
        status_counts[s] = status_counts.get(s, 0) + 1

    om1, om2, om3, om4 = st.columns(4)
    om1.metric("Not started", status_counts.get("not_started", 0))
    om2.metric("In progress", status_counts.get("in_progress", 0))
    om3.metric("Applied", status_counts.get("applied", 0))
    om4.metric("Accepted", status_counts.get("accepted", 0))

    st.divider()

    # Two-column grid for cards
    columns = st.columns(2)
    for i, card in enumerate(cards):
        col = columns[i % 2]
        with col, st.container(border=True):
            head = st.columns([4, 1])
            with head[0]:
                st.markdown(f"**{card['name']}**")
                st.caption(card["category"])
            with head[1]:
                st.markdown(
                    f'<span class="status-chip {card["status"]}">{card["status"]}</span>',
                    unsafe_allow_html=True,
                )
            if card.get("url"):
                st.markdown(f"[{card['url']}]({card['url']})")
            st.markdown(f"**Target rate:** €{card.get('target_rate_eur', '—')}/hr")
            with st.expander("Profile keywords & next action"):
                st.markdown(f"```\n{card.get('profile_keywords', '')}\n```")
                st.markdown(f"**Next action:** {card.get('next_action') or '_(none)_'}")
            new_status = st.selectbox(
                "Update status",
                _ONBOARDING_STATUSES,
                index=_ONBOARDING_STATUSES.index(card["status"]),
                key=f"status-{card['id']}",
            )
            if new_status != card["status"]:
                update_onboarding_status(str(card["id"]), new_status)
                st.rerun()

# ═══════════════════════════════════════════════════════════════════════════
#  OBSERVABILITY
# ═══════════════════════════════════════════════════════════════════════════
with tab_observability:
    runs = list_source_runs(limit=40)

    if runs:
        # Aggregate per-source totals from the last 40 runs
        per_source: dict[str, dict[str, int]] = {}
        for r in runs:
            s = r.get("source", "?")
            bucket = per_source.setdefault(s, {"runs": 0, "found": 0, "new": 0, "errors": 0})
            bucket["runs"] += 1
            bucket["found"] += r.get("listings_found") or 0
            bucket["new"] += r.get("listings_new") or 0
            if r.get("error"):
                bucket["errors"] += 1

        cols = st.columns(len(per_source) or 1)
        for col, (source, stats) in zip(cols, sorted(per_source.items()), strict=False):
            with col, st.container(border=True):
                st.markdown(
                    f'<span class="source-pill">{_SOURCE_LABELS.get(source, source)}</span>',
                    unsafe_allow_html=True,
                )
                st.metric("Runs", stats["runs"])
                st.caption(
                    f"{stats['found']} found · {stats['new']} new"
                    + (f" · ⚠ {stats['errors']} errors" if stats["errors"] else "")
                )

        st.divider()

    st.markdown("**Recent runs**")
    st.dataframe(
        runs,
        use_container_width=True,
        hide_index=True,
        column_order=("started_at", "source", "listings_found", "listings_new", "error"),
        column_config={
            "started_at": st.column_config.DatetimeColumn("Started", format="MMM D, HH:mm:ss"),
            "source": "Source",
            "listings_found": st.column_config.NumberColumn("Found"),
            "listings_new": st.column_config.NumberColumn("New"),
            "error": "Error",
        },
    )

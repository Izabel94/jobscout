"""DOM-aware page classification for the apply flow.

Hardcoded URL/selector/keyword checks mislabel pages — a submit whose button
text isn't in a keyword list is never recorded, and a page that isn't a form
gets guessed at. Instead, read what is actually on the page and let the LLM
judge its state from that evidence.

Two uses:
  * decide login-vs-unavailable-vs-form when an apply is blocked, and
  * detect a real submission by its confirmation page (not a click listener
    that misses clicks / iframes / late clicks).
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from playwright.sync_api import Page

from jobscout.llm import call_json

# jobscout pins the apply LLM to this model (see external_ats._ask_llm_for_actions).
_CLASSIFY_MODEL = "gemini-3.1-flash-lite"


class PageState(StrEnum):
    APPLICATION_FORM = "application_form"  # a fillable application form is present
    LOGIN_REQUIRED = "login_required"  # must sign in before applying
    SUBMITTED = "submitted"  # confirmation / "application received"
    UNAVAILABLE = "unavailable"  # private, closed, expired, removed, not found
    OTHER = "other"  # e.g. a job description whose apply CTA isn't clicked yet


@dataclass(frozen=True)
class PageAssessment:
    state: PageState
    reason: str

    @property
    def blocked(self) -> bool:
        """Can't auto-fill from here (needs the user or is a dead end)."""
        return self.state in (PageState.LOGIN_REQUIRED, PageState.UNAVAILABLE)


# Visible, bounded view of the page. Visibility is checked so hidden template
# nodes don't pollute the evidence.
_SNAPSHOT_JS = """() => {
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden'; };
  const texts = (sel, n) => [...document.querySelectorAll(sel)].filter(vis)
    .map(e => (e.innerText||e.textContent||'').trim()).filter(Boolean).slice(0, n);
  const body = (document.body ? (document.body.innerText||'') : '').replace(/\\s+/g,' ').trim().slice(0, 2500);
  return {
    title: document.title || '',
    headings: texts('h1,h2,h3', 8),
    buttons: texts('button,[role=button],a.btn,a.button,input[type=submit]', 20),
    has_password: [...document.querySelectorAll('input[type=password]')].some(vis),
    field_count: [...document.querySelectorAll('input,select,textarea')].filter(vis).length,
    body_text: body,
  };
}"""


def snapshot(page: Page) -> dict[str, Any]:
    """Bounded, structured view of what's visibly on the page. Deterministic —
    no LLM."""
    snap: dict[str, Any] = {"url": getattr(page, "url", "")}
    with contextlib.suppress(Exception):
        snap.update(page.evaluate(_SNAPSHOT_JS))
    return snap


_SYSTEM = (
    "You classify the current state of a web page in a job-application flow, "
    "using ONLY the provided evidence (url, title, headings, button labels, "
    "visible body text, whether a password field is present).\n"
    'Respond with strict JSON: {"state": <one value>, "reason": <short phrase>}.\n'
    "state is exactly one of:\n"
    "- application_form: a fillable job-application form is present (name/email/"
    "cover-letter/upload fields for THIS application).\n"
    "- login_required: you must sign in / create an account before you can apply "
    "(a login or register form, or an explicit 'sign in to apply' prompt).\n"
    "- submitted: the application was sent — a confirmation, thank-you, or "
    "'application received / already applied' page.\n"
    "- unavailable: the listing is private, closed, expired, filled, removed, or "
    "not found.\n"
    "- other: none of the above (e.g. a job description whose apply button hasn't "
    "been clicked yet).\n"
    "Do NOT assume login_required just because there is no form: a private or "
    "closed listing is 'unavailable'. A password field strongly indicates "
    "login_required, but a private/closed message means 'unavailable'."
)


def classify_page(page: Page, *, model: str = _CLASSIFY_MODEL) -> PageAssessment:
    """LLM judgment of the page's state from its actual content. On any failure
    returns OTHER with a reason, so callers keep their own fallback guards
    rather than acting on a bad classification."""
    snap = snapshot(page)
    try:
        result = call_json(
            model=model,
            system=_SYSTEM,
            user=json.dumps(snap, ensure_ascii=False),
            max_tokens=200,
        )
    except Exception as e:  # never let a classification failure crash the apply flow
        return PageAssessment(PageState.OTHER, f"classify_failed:{type(e).__name__}")
    raw = str(result.get("state", "")).strip().lower()
    try:
        state = PageState(raw)
    except ValueError:
        state = PageState.OTHER
    return PageAssessment(state, str(result.get("reason", ""))[:200])

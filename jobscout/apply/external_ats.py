"""Generic external-ATS auto-fill.

Drives any single-page apply form (Greenhouse, Lever, Ashby, Workable,
Personio, Bundesagentur externeUrl, LinkedIn external redirect, etc.) up
to the Submit step; the user clicks Submit.

Flow: attach to CDP Chrome → walk apply-CTA hops → enumerate fields →
one LLM call to map fields to actions → apply each action → pause.

We reuse the `JOBSCOUT_CDP_URL` env var — same CDP Chrome instance for all
auto-apply flows.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from jobscout.llm import LLMJSONError, call_json


class EasyApplyAfterClickError(RuntimeError):
    """Raised when the apply flow reaches the form still on linkedin.com despite
    the listing being classified as EXTERNAL_APPLY — i.e. LinkedIn's in-app apply
    (classic /jobs/easyApply/ or the newer SDUI /jobs/view/<id>/apply overlay),
    which we can't fill. The worker catches this, marks the apply_request failed,
    and flips listings.apply_method to easy_apply so the row surfaces under the
    manual section next time.
    """


class ApplyOutcome(StrEnum):
    """What the apply flow observed. The worker maps each to a DB transition;
    only SUBMITTED records a submission."""

    SUBMITTED = "submitted"
    FILLED_NO_SUBMIT = "filled_no_submit"
    NOT_FILLABLE = "not_fillable"


@dataclass
class ApplyResult:
    outcome: ApplyOutcome
    reason: str | None = None  # set for NOT_FILLABLE, e.g. "login_wall"


_EASY_APPLY_HOST_FRAGMENT = "linkedin.com"


def _assert_not_easy_apply(page: Page) -> None:
    # A genuine external apply redirects off LinkedIn to the employer's ATS.
    # If we've reached the form and are still on linkedin.com, it's the in-app
    # apply (classic /jobs/easyApply/ or the SDUI /apply overlay, which keeps the
    # /jobs/view/<id>/ URL) — not fillable, so surface it for manual apply.
    url = (page.url or "").lower()
    if _EASY_APPLY_HOST_FRAGMENT in url:
        raise EasyApplyAfterClickError(f"still on LinkedIn at form step (Easy Apply): {page.url}")


_PAGE_THINK_SECONDS = (10.0, 18.0)
_FIELD_THINK_SECONDS = (0.6, 1.8)
_INTER_ROUND_WAIT_MS = 1_500
_MAX_ROUNDS = 5
_MAX_PAGE_ADVANCES = 3

# Apply order within a round: selects/checks first (a phone-country dropdown
# must be set before the number is typed, else an intl-tel field resets to the
# dial code), then type/paste, then attach (a CV upload often re-renders and
# clears prior fills), skip last.
_ACTION_PRIORITY = {"select": 0, "check": 0, "uncheck": 0, "type": 1, "paste": 1, "attach": 2, "skip": 3}

# Buttons safe to click to reach the next page of a multi-step form.
_NEXT_KEYWORDS = ("next", "continue", "weiter", "proceed", "nächste", "next step")
# NEVER click these — final submit is always the user's, even if the text also
# contains a _NEXT_KEYWORD (e.g. "Next: Submit").
_NEVER_CLICK_KEYWORDS = (
    "submit", "apply", "send", "abschicken", "absenden", "finish", "fertig",
    "complete", "abschließen",
)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "prompts"
_PROMPT_PATH = _PROMPTS_DIR / "ats_form_fill.v1.md"

# Bundesagentur externeUrl → job-board listing → employer form chain — 3 hops covers it.
_MAX_APPLY_HOPS = 3

_APPLY_CTA_KEYWORDS = (
    "jetzt bewerben",
    "bewerben",
    "apply now",
    "apply for this",
    "apply",
    "submit application",
    "start application",
    "bewerbung",
)

# "Apply later" / save-for-later decoys — never the real apply CTA (join.com
# shows a "Später bewerben" email-capture next to "Jetzt bewerben").
_APPLY_LATER_KEYWORDS = ("später", "spater", "later", "merken", "save")

# SSO / social-login buttons — never click these to advance (they open a
# third-party auth popup). e.g. join.com's "Weiter mit Google".
_SSO_KEYWORDS = ("google", "apple", "facebook", "linkedin", "microsoft", "sso", "single sign")


# Capture-phase click listener that fires the moment the user clicks a
# final-submit button — synchronously, before any navigation wipes the page.
# add_init_script reinstalls it on every navigation and new tab, so multi-step
# forms and post-submit redirects stay covered. The handler reports back to
# Python via the __jsNotifySubmit binding so the signal survives the redirect.
_SUBMIT_DETECTOR_JS = """
(keywords) => {
  if (window.__jsSubmitHooked) return;
  window.__jsSubmitHooked = true;
  document.addEventListener('click', (e) => {
    const t = e.target;
    if (!t || !t.closest) return;
    const el = t.closest('button, [role=button], input[type=submit], input[type=button], a');
    if (!el) return;
    const txt = (el.innerText || el.value || el.textContent || '').trim().toLowerCase();
    if (keywords.some((k) => txt.includes(k)) && window.__jsNotifySubmit) {
      window.__jsNotifySubmit(txt.slice(0, 120));
    }
  }, true);
}
"""


def _install_submit_detector(context: BrowserContext, page: Page) -> dict[str, Any]:
    """Watch for the user clicking a final-submit button. Returns a mutable
    state dict whose `clicked` flag flips True when a submit click is seen."""
    state: dict[str, Any] = {"clicked": False, "text": None}

    def _on_submit(_source: dict[str, Any], text: str) -> None:
        state["clicked"] = True
        state["text"] = text

    with contextlib.suppress(Exception):
        context.expose_binding("__jsNotifySubmit", _on_submit)
    keywords = list(_NEVER_CLICK_KEYWORDS)
    # add_init_script (no args in the sync API) covers future navigations and
    # new tabs; embed the keywords via JSON and self-invoke. evaluate once more
    # for the page that's already loaded.
    init_script = f"(() => {{ ({_SUBMIT_DETECTOR_JS})({json.dumps(keywords)}); }})()"
    with contextlib.suppress(Exception):
        context.add_init_script(init_script)
    with contextlib.suppress(Exception):
        page.evaluate(_SUBMIT_DETECTOR_JS, keywords)
    return state


def _think_pause(page: Page, seconds_range: tuple[float, float], label: str) -> None:
    lo, hi = seconds_range
    secs = random.uniform(lo, hi)
    print(f"  {label}: thinking for {secs:.1f}s…", flush=True)
    page.wait_for_timeout(int(secs * 1000))


# --- DOM enumeration ---------------------------------------------------------

# Single page.evaluate for a consistent snapshot. Each field is marked
# with a `data-ats-id` so selectors survive re-renders that would break CSS paths.
_ENUM_JS = r"""
() => {
  const fields = [];
  // Stable, monotonic ids across re-enumerations: reuse an element's existing
  // id, and seed the counter from a window-level value so a later page's new
  // fields get fresh ids instead of colliding with an earlier page's __ats_0..N
  // (which would make the round loop treat them as already-seen).
  window.__jsAtsN = window.__jsAtsN || 0;
  const mark = (el) => {
    let id = el.getAttribute('data-ats-id');
    if (id) return id;
    id = `__ats_${window.__jsAtsN++}`;
    el.setAttribute('data-ats-id', id);
    return id;
  };
  const visible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  };
  const labelFor = (el) => {
    // explicit <label for="id">
    if (el.id) {
      const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lbl) return (lbl.textContent || '').trim().slice(0, 200);
    }
    // wrapping <label>
    const wrap = el.closest('label');
    if (wrap) return (wrap.textContent || '').trim().slice(0, 200);
    // aria-label / aria-labelledby
    const aria = el.getAttribute('aria-label');
    if (aria) return aria.slice(0, 200);
    const byid = el.getAttribute('aria-labelledby');
    if (byid) {
      const ref = document.getElementById(byid);
      if (ref) return (ref.textContent || '').trim().slice(0, 200);
    }
    // climb up: nearest preceding heading / .label / .field-label
    let p = el.parentElement;
    while (p) {
      const cand = p.querySelector(':scope > label, :scope > .label, :scope > [class*=label], :scope > h2, :scope > h3, :scope > legend');
      if (cand && !cand.contains(el)) return (cand.textContent || '').trim().slice(0, 200);
      p = p.parentElement;
    }
    // fallback: placeholder
    return (el.placeholder || '').slice(0, 200);
  };

  // text-like inputs
  const textTypes = ['text','email','tel','url','number','search'];
  document.querySelectorAll('input').forEach(el => {
    const t = (el.type || 'text').toLowerCase();
    if (!textTypes.includes(t)) return;
    if (!visible(el)) return;
    fields.push({
      id: mark(el),
      kind: t === 'email' ? 'email' : (t === 'tel' ? 'tel' : (t === 'url' ? 'url' : (t === 'number' ? 'number' : 'text'))),
      label: labelFor(el),
      required: !!el.required,
      placeholder: el.placeholder || '',
      currentValue: el.value || '',
    });
  });

  // textareas
  document.querySelectorAll('textarea').forEach(el => {
    if (!visible(el)) return;
    fields.push({
      id: mark(el),
      kind: 'textarea',
      label: labelFor(el),
      required: !!el.required,
      currentValue: el.value || '',
    });
  });

  // selects
  document.querySelectorAll('select').forEach(el => {
    if (!visible(el)) return;
    fields.push({
      id: mark(el),
      kind: 'select',
      label: labelFor(el),
      required: !!el.required,
      options: Array.from(el.options).map(o => o.text).slice(0, 80),
      currentValue: el.value || '',
    });
  });

  // checkboxes + radios (each as its own field — the LLM decides per item)
  document.querySelectorAll('input[type="checkbox"], input[type="radio"]').forEach(el => {
    if (!visible(el)) return;
    fields.push({
      id: mark(el),
      kind: el.type,  // 'checkbox' | 'radio'
      label: labelFor(el),
      required: !!el.required,
      currentValue: el.checked ? 'checked' : 'unchecked',
      groupName: el.name || '',
    });
  });

  // file inputs (resume / CV upload)
  document.querySelectorAll('input[type="file"]').forEach(el => {
    // not requiring visible — these are often inside a styled "Upload" button
    fields.push({
      id: mark(el),
      kind: 'file',
      label: labelFor(el),
      required: !!el.required,
      accept: el.accept || '',
    });
  });

  return fields;
}
"""


def _enumerate_fields(page: Page) -> list[dict[str, Any]]:
    return page.evaluate(_ENUM_JS) or []


def _select_round_targets(fields: list[dict[str, Any]], seen_ids: set[str]) -> list[dict[str, Any]]:
    """Pure helper — round 2+ target selection.

    Returns the subset of `fields` the LLM should be asked about in this round:
      - any field whose id wasn't in a previous round's prompt, AND
      - any field already seen but whose currentValue is now empty (re-render
        cleared a previously-filled textarea, common with React-based ATS forms
        where a CV upload triggers form-state reset of the cover letter field).

    Checkbox / radio fields use 'checked' / 'unchecked' for currentValue —
    'unchecked' is a meaningful state, not 'empty', so don't re-target those.
    """
    empty_markers = ("", None)
    targets: list[dict[str, Any]] = []
    for f in fields:
        fid = f.get("id")
        if not isinstance(fid, str):
            continue
        if fid not in seen_ids:
            targets.append(f)
            continue
        kind = (f.get("kind") or "").lower()
        if kind in ("checkbox", "radio"):
            continue  # already-seen checkbox state is meaningful even if "unchecked"
        if kind == "file":
            continue  # file inputs always report empty currentValue (browser
            # security) — re-targeting would re-attach the same CV every round
        current = f.get("currentValue")
        if isinstance(current, str):
            current = current.strip()
        if current in empty_markers:
            targets.append(f)
    return targets


# --- LLM mapping -------------------------------------------------------------


def _render_field_list(fields: list[dict[str, Any]]) -> str:
    lines = []
    for i, f in enumerate(fields):
        bits = [f"[{i}] selector=`[data-ats-id=\"{f['id']}\"]` kind={f['kind']}"]
        if f.get("required"):
            bits.append("REQUIRED (Pflichtfeld)")
        label = f.get("label") or "(no label)"
        bits.append(f"label={label!r}")
        if f.get("placeholder"):
            bits.append(f"placeholder={f['placeholder']!r}")
        if f.get("options"):
            opts = ", ".join(f["options"])
            bits.append(f"options=[{opts}]")
        if f.get("groupName"):
            bits.append(f"group={f['groupName']!r}")
        if f.get("currentValue"):
            bits.append(f"current={f['currentValue']!r}")
        lines.append("  - " + " | ".join(bits))
    return "\n".join(lines)


def _candidate_context(profile_row: dict[str, Any]) -> dict[str, str]:
    """Map a jobscout `profiles` row to the placeholder dict the prompt template expects."""
    languages = profile_row.get("languages") or {}
    lang_lines = (
        "\n".join(f"  - {lang}: {level}" for lang, level in languages.items())
        if languages
        else "  (none configured)"
    )
    rate_eur = profile_row.get("target_rate_floor_eur")
    salary_eur = profile_row.get("target_salary_eur")
    return {
        "target_salary_eur": "" if salary_eur is None else str(int(salary_eur)),
        "candidate_name": str(profile_row.get("full_name", "")),
        "candidate_email": str(profile_row.get("email", "")),
        "candidate_phone": str(profile_row.get("phone", "")),
        "candidate_location": str(profile_row.get("location", "")),
        "candidate_linkedin": str(profile_row.get("linkedin_url", "")),
        "candidate_portfolio": "",
        "years_experience": str(profile_row.get("years_experience") or ""),
        "available_hours_per_week": "",
        "target_rate_eur_hr": "" if rate_eur is None else str(rate_eur),
        "target_rate_usd_hr": "",
        "work_authorization": "",
        "sensitive_defaults": "  (none configured)",
        "candidate_languages": lang_lines,
    }


def _ask_llm_for_actions(
    *,
    fields: list[dict[str, Any]],
    cover_letter: str,
    adapted_cv: str,
    listing_title: str,
    listing_description: str,
) -> list[dict[str, Any]]:
    """Raises LLMJSONError on malformed output."""
    from jobscout.db import get_profile

    linkedin_url = os.environ["JOBSCOUT_PROFILE_LINKEDIN_URL"]
    profile_row = get_profile(linkedin_url)
    if profile_row is None:
        raise RuntimeError(f"no profiles row for {linkedin_url!r}")
    ctx = _candidate_context(profile_row)
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    rendered = (
        template.replace("{{numbered_fields}}", _render_field_list(fields))
        .replace("{{cover_letter}}", cover_letter)
        .replace("{{adapted_cv}}", (adapted_cv or "")[:6000])
        .replace("{{listing_title}}", listing_title or "")
        .replace("{{listing_description}}", (listing_description or "")[:4000])
    )
    for k, v in ctx.items():
        rendered = rendered.replace(f"{{{{{k}}}}}", v)
    result = call_json(
        model="gemini-3.1-flash-lite",
        system="You fill out job-application forms conservatively and concisely.",
        user=rendered,
        max_tokens=4000,
    )
    actions = result.get("actions")
    if not isinstance(actions, list):
        raise LLMJSONError(f"expected 'actions' array, got {actions!r}")
    return [a for a in actions if isinstance(a, dict)]


# --- Field filling -----------------------------------------------------------


def _apply_action(
    page: Page,
    action: dict[str, Any],
    cv_pdf_path: Path | None,
    cover_letter: str,
    cover_letter_pdf_path: Path | None = None,
) -> tuple[bool, str]:
    """Returns (applied, note). `@cover_letter` and `cv_pdf` are LLM-friendly sentinels resolved here."""
    selector = action.get("selector") or ""
    kind = (action.get("action") or "").lower()
    value = action.get("value", "")
    if isinstance(value, str) and value.strip() in ("@cover_letter", "cover_letter"):
        value = cover_letter

    if kind == "skip":
        return True, "skipped"

    if not selector:
        return False, "no selector"

    try:
        loc = page.locator(selector).first
        if loc.count() == 0:
            return False, "selector not found"

        if kind in ("type", "paste"):
            with contextlib.suppress(Exception):
                loc.scroll_into_view_if_needed(timeout=2_000)
            loc.click()
            input_type = ""
            with contextlib.suppress(Exception):
                input_type = (loc.evaluate("el => el.type || ''") or "").lower()
            if input_type == "tel":
                # intl-tel widgets with a separate country selector want the
                # NATIONAL number; typing the full "+49 163…" mangles it (the
                # widget re-prepends the dial code). fill() also gets dropped —
                # use real keystrokes. Strip a leading "+CC " prefix.
                phone = str(value).strip()
                if phone.startswith("+") and " " in phone:
                    phone = phone.split(" ", 1)[1].strip()
                with contextlib.suppress(Exception):
                    loc.fill("")
                loc.press_sequentially(phone, delay=40)
                return True, "filled (tel national keystrokes)"
            loc.fill(str(value))
            return True, "filled"

        if kind == "select":
            with contextlib.suppress(Exception):
                loc.scroll_into_view_if_needed(timeout=2_000)
            try:
                loc.select_option(label=str(value))
            except (PlaywrightTimeoutError, Exception):
                loc.select_option(value=str(value))
            return True, f"selected {value!r}"

        if kind == "check":
            loc.check()
            return True, "checked"

        if kind == "uncheck":
            loc.uncheck()
            return True, "unchecked"

        if kind == "attach":
            if value == "cover_letter_pdf":
                if cover_letter_pdf_path is None or not cover_letter_pdf_path.exists():
                    return False, f"attach skipped (cover_letter_pdf missing: {cover_letter_pdf_path})"
                loc.set_input_files(str(cover_letter_pdf_path))
                return True, f"attached {cover_letter_pdf_path.name}"
            if value != "cv_pdf" or cv_pdf_path is None or not cv_pdf_path.exists():
                return False, f"attach skipped (value={value!r}, cv_pdf={cv_pdf_path})"
            loc.set_input_files(str(cv_pdf_path))
            return True, f"attached {cv_pdf_path.name}"

        return False, f"unknown action {kind!r}"
    except (PlaywrightTimeoutError, Exception) as e:
        return False, f"error: {e}"


# --- Page + tab plumbing -----------------------------------------------------


def _dismiss_consent_banner(page: Page) -> bool:
    """Inject `!important` CSS to keep banners hidden across re-renders, then click Accept so consent is genuinely recorded."""
    return page.evaluate(
        """() => {
          // Step 1: persistent CSS that survives re-renders.
          const styleId = '__jobscout_consent_kill';
          if (!document.getElementById(styleId)) {
            const style = document.createElement('style');
            style.id = styleId;
            style.textContent = `
              #usercentrics-cmp-ui,
              #onetrust-banner-sdk,
              #onetrust-pc-sdk,
              #CybotCookiebotDialog,
              #CybotCookiebotDialogBodyUnderlay,
              .klaro,
              .cli-modal,
              .cookie-banner,
              .cookie-consent,
              [class*="cookie-consent"],
              [id*="cookie-banner"],
              [class*="cookie-modal"] {
                display: none !important;
                pointer-events: none !important;
                visibility: hidden !important;
                opacity: 0 !important;
              }
            `;
            document.documentElement.appendChild(style);
          }

          // Step 2: actually click Accept so the host site records consent.
          let clicked = false;
          const trySelectors = [
            'button[data-testid="uc-accept-all-button"]',
            'button[aria-label*="Accept all" i]',
            'button[aria-label*="Alle akzeptieren" i]',
            'button#onetrust-accept-btn-handler',
            '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
            'button.cookie-accept-all',
          ];
          for (const sel of trySelectors) {
            const el = document.querySelector(sel);
            if (el) { el.click(); clicked = true; break; }
          }
          // Usercentrics renders inside Shadow DOM
          if (!clicked) {
            const ucHost = document.querySelector('#usercentrics-cmp-ui');
            if (ucHost && ucHost.shadowRoot) {
              const buttons = ucHost.shadowRoot.querySelectorAll('button');
              for (const b of buttons) {
                const txt = (b.textContent || '').toLowerCase();
                if (txt.includes('accept') || txt.includes('akzeptieren') ||
                    txt.includes('zustimmen') || txt.includes('save')) {
                  b.click();
                  clicked = true;
                  break;
                }
              }
            }
          }
          return true;
        }"""
    )


def _find_apply_cta(page: Page) -> str | None:
    """Return href of the first visible Apply / Bewerben anchor.

    Skips elements with long text — on LinkedIn the "similar jobs" cards are
    `<a>` wrappers whose textContent includes an "Easy Apply" badge, which
    would otherwise match. The real apply button has short text ("Bewerben").
    """
    return page.evaluate(
        """(keywords) => {
          const candidates = Array.from(document.querySelectorAll('a, button, [role="button"]'));
          for (const el of candidates) {
            const own = (el.textContent || '').trim();
            if (own.length > 60) continue;  // skip job-card wrappers
            const text = (own + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase().trim();
            if (!text) continue;
            const matches = keywords.some(k => text.includes(k));
            if (!matches) continue;
            const r = el.getBoundingClientRect();
            const cs = getComputedStyle(el);
            if (r.width === 0 || r.height === 0 || cs.display === 'none' || cs.visibility === 'hidden') continue;
            return el.href || null;
          }
          return null;
        }""",
        list(_APPLY_CTA_KEYWORDS),
    )


def _resolve_cta_href(href: str) -> str:
    """Unwrap LinkedIn's `safety/go/?url=<encoded>` redirect to the real
    destination, skipping the "you're leaving LinkedIn" interstitial. Other
    hrefs pass through unchanged."""
    if "linkedin.com/safety/go" not in href:
        return href
    parsed = urlparse(href)
    target = parse_qs(parsed.query).get("url", [None])[0]
    return unquote(target) if target else href


def _looks_like_form(fields: list[dict[str, Any]]) -> bool:
    """True when the enumerated fields look like a real application form, not
    a listing page with a stray field or two (e.g. LinkedIn's language picker).
    A real form has a file input, a textarea, or several fields."""
    if any(f.get("kind") == "file" for f in fields):
        return True
    if any(f.get("kind") == "textarea" for f in fields):
        return True
    return len(fields) >= 3


def _has_password_field(page: Page) -> bool:
    """A visible password input means a login/register widget — never a real
    job application form. Used to keep the walker from mistaking a sign-in box
    for the application and to flag login walls as manual."""
    try:
        return bool(
            page.evaluate(
                "() => [...document.querySelectorAll('input[type=password]')]"
                ".some(e => { const r = e.getBoundingClientRect();"
                " return r.width > 0 && r.height > 0; })"
            )
        )
    except Exception:
        return False


def _advance_to_next_step(page: Page) -> bool:
    """Click a strictly-allowlisted 'next page' button to reveal the next step
    of a multi-page form. NEVER clicks final-submit buttons — submitting is
    always the user's action. Returns True if it advanced."""
    marked = page.evaluate(
        """(kw) => {
          const isNext = t => kw.next.some(n => t.includes(n));
          const isNever = t => kw.never.some(n => t.includes(n));
          const isSso = t => kw.sso.some(n => t.includes(n));
          for (const el of document.querySelectorAll('button, [role="button"], a')) {
            const t = (el.textContent || '').trim().toLowerCase();
            if (!t || t.length > 25) continue;
            if (isNever(t)) continue;        // submit/apply/etc. take precedence
            if (isSso(t)) continue;          // skip "Weiter mit Google" etc.
            if (!isNext(t)) continue;
            if (el.disabled) continue;
            const r = el.getBoundingClientRect();
            const cs = getComputedStyle(el);
            if (r.width === 0 || r.height === 0 || cs.display === 'none' || cs.visibility === 'hidden') continue;
            el.setAttribute('data-js-next', '1');
            return true;
          }
          return false;
        }""",
        {"next": list(_NEXT_KEYWORDS), "never": list(_NEVER_CLICK_KEYWORDS), "sso": list(_SSO_KEYWORDS)},
    )
    if not marked:
        return False
    try:
        page.locator('[data-js-next]').first.click(timeout=4_000)
        page.wait_for_timeout(_INTER_ROUND_WAIT_MS)
        return True
    except (PlaywrightTimeoutError, Exception) as e:
        print(f"  next-step click failed: {e}", flush=True)
        return False
    finally:
        with contextlib.suppress(Exception):
            page.evaluate(
                "() => document.querySelectorAll('[data-js-next]')"
                ".forEach(e => e.removeAttribute('data-js-next'))"
            )


def _click_apply_cta(page: Page) -> bool:
    """Click a visible Apply/Bewerben CTA that has no link to follow (a button,
    or an <a> with no usable href) — e.g. join.com's 'Jetzt bewerben' which
    starts the apply flow via JS. Skips 'apply later' decoys and SSO buttons.
    Direct-nav by href is preferred; this is the fallback. Returns True if it
    clicked one (the flow usually navigates the same tab)."""
    marked = page.evaluate(
        """(kw) => {
          const has = (t, list) => list.some(k => t.includes(k));
          for (const el of document.querySelectorAll('a, button, [role="button"]')) {
            const own = (el.textContent || '').trim();
            if (!own || own.length > 60) continue;
            const t = (own + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase();
            if (!has(t, kw.apply)) continue;
            if (has(t, kw.later) || has(t, kw.sso)) continue;
            if (el.tagName === 'A' && el.href && !el.href.endsWith('#')) continue;  // real link -> direct-nav handles it
            const r = el.getBoundingClientRect();
            const cs = getComputedStyle(el);
            if (r.width === 0 || r.height === 0 || cs.display === 'none' || cs.visibility === 'hidden') continue;
            el.setAttribute('data-js-cta', '1');
            return true;
          }
          return false;
        }""",
        {"apply": list(_APPLY_CTA_KEYWORDS), "later": list(_APPLY_LATER_KEYWORDS), "sso": list(_SSO_KEYWORDS)},
    )
    if not marked:
        return False
    try:
        page.locator('[data-js-cta]').first.click(timeout=5_000)
        page.wait_for_timeout(2_500)
        return True
    except (PlaywrightTimeoutError, Exception) as e:
        print(f"  apply-button click failed: {e}", flush=True)
        return False
    finally:
        with contextlib.suppress(Exception):
            page.evaluate("() => document.querySelectorAll('[data-js-cta]').forEach(e => e.removeAttribute('data-js-cta'))")


def _walk_to_form(context: BrowserContext, page: Page) -> Page:
    """Follow Apply CTAs until the page is an actual application form, up to
    _MAX_APPLY_HOPS. A page with only stray fields (a job-view, or an
    'apply later' email box) but a visible apply CTA is NOT the form — follow
    the link, or click the button when there's no link."""
    for hop in range(_MAX_APPLY_HOPS):
        fields = _enumerate_fields(page)
        # A login/register widget (password field) is not the application form.
        if _looks_like_form(fields) and not _has_password_field(page):
            return page
        cta_href = _find_apply_cta(page)
        if cta_href:
            cta_href = _resolve_cta_href(cta_href)
            print(f"  hop {hop + 1}/{_MAX_APPLY_HOPS}: following apply CTA -> {cta_href[:90]}", flush=True)
            # Direct nav beats clicking — JS handlers often call window.open which
            # is blocked for non-trusted events.
            try:
                new_page = context.new_page()
                new_page.goto(cta_href, wait_until="domcontentloaded", timeout=30_000)
                new_page.wait_for_timeout(2_000)
                if hop > 0:
                    with contextlib.suppress(Exception):
                        page.close()
                page = new_page
                with contextlib.suppress(Exception):
                    page.bring_to_front()
            except Exception as e:
                print(f"  hop failed: {e}", flush=True)
                return page
            continue
        # No link to follow — try clicking a button CTA (JS-driven apply flow).
        if _click_apply_cta(page):
            print(f"  hop {hop + 1}/{_MAX_APPLY_HOPS}: clicked apply button -> {page.url[:90]}", flush=True)
            continue
        return page
    return page


def _find_or_open_target_page(context: BrowserContext, ats_url: str) -> Page:
    """Reuse a tab on the same host, but always navigate it to the target URL —
    otherwise a stray same-host tab (e.g. the linkedin.com/feed page the apply
    Chrome opens on) gets mistaken for the job and 'filled'. Opens a new tab if
    no same-host one exists."""
    target_host = (urlparse(ats_url).hostname or "").lower()
    want = (ats_url or "").rstrip("/")
    for pg in context.pages:
        try:
            host = (urlparse(pg.url).hostname or "").lower()
        except Exception:
            continue
        if host and host == target_host:
            if (pg.url or "").rstrip("/") != want:
                with contextlib.suppress(Exception):
                    pg.goto(ats_url, wait_until="domcontentloaded", timeout=30_000)
                    pg.wait_for_timeout(1_500)
            return pg
    page = context.new_page()
    page.goto(ats_url, wait_until="domcontentloaded", timeout=30_000)
    return page


# --- Public API --------------------------------------------------------------


# How long to keep the filled tab open waiting for the user to click Submit.
# Bounded so the worker exits cleanly (exit 0) rather than being killed by the
# launchd wrapper's gtimeout backstop — a timeout there would read as a failure.
_SUBMIT_WAIT_SECONDS = 600


def _await_user_submit(
    page: Page, submit_state: dict[str, Any], max_wait_seconds: float = _SUBMIT_WAIT_SECONDS
) -> ApplyResult:
    """Leave the filled tab open for the user to review and submit. Record a
    submission ONLY when a final-submit click is observed; closing the tab — or
    walking away — without that click is FILLED_NO_SUBMIT, never a phantom
    submission."""
    deadline = time.monotonic() + max_wait_seconds
    while time.monotonic() < deadline:
        if submit_state.get("clicked"):
            print("  submit click detected — recording submission", flush=True)
            return ApplyResult(ApplyOutcome.SUBMITTED)
        try:
            page.wait_for_event("close", timeout=1_000)
        except PlaywrightTimeoutError:
            continue
        outcome = ApplyOutcome.SUBMITTED if submit_state.get("clicked") else ApplyOutcome.FILLED_NO_SUBMIT
        print(f"  tab closed — outcome={outcome.value}", flush=True)
        return ApplyResult(outcome)
    print("  no submit within wait window — leaving tab open, marking attempted", flush=True)
    return ApplyResult(ApplyOutcome.FILLED_NO_SUBMIT)


def apply(
    *,
    ats_url: str,
    proposal: str,
    cv_pdf_path: Path | None,
    listing_title: str,
    listing_description: str,
    adapted_cv_md: str,
    cover_letter_pdf_path: Path | None = None,
) -> ApplyResult:
    cdp_url = os.environ.get("JOBSCOUT_CDP_URL")
    if not cdp_url:
        print(
            "JOBSCOUT_CDP_URL not set. Launch the CDP Chrome first:\n"
            "    bash scripts/chrome-cdp.sh\n"
            "then re-run with JOBSCOUT_CDP_URL=http://localhost:9223",
            flush=True,
        )
        sys.exit(2)
    with sync_playwright() as p:
        return _run(
            p, cdp_url, ats_url, proposal, cv_pdf_path,
            listing_title, listing_description, adapted_cv_md, cover_letter_pdf_path,
        )


def _run(
    p: Playwright,
    cdp_url: str,
    ats_url: str,
    proposal: str,
    cv_pdf_path: Path | None,
    listing_title: str,
    listing_description: str,
    adapted_cv_md: str,
    cover_letter_pdf_path: Path | None = None,
) -> ApplyResult:
    print(f"Attaching to Chrome via {cdp_url}", flush=True)
    browser = p.chromium.connect_over_cdp(cdp_url)
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    try:
        page = _find_or_open_target_page(context, ats_url)
        with contextlib.suppress(Exception):
            page.bring_to_front()
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
        page.wait_for_timeout(2_000)

        print(f"On {page.url}", flush=True)

        page = _walk_to_form(context, page)
        print(f"Form page: {page.url}", flush=True)

        _assert_not_easy_apply(page)

        # Still on a login/register page after walking the apply CTAs -> the
        # application is behind a sign-in we can't pass. Don't fill the login
        # form; flag it for manual apply.
        if _has_password_field(page):
            print(
                "Apply is behind a login (password field present). Sign in on that "
                "site once in this Chrome, or apply manually. Flagging for manual apply.",
                flush=True,
            )
            return ApplyResult(ApplyOutcome.NOT_FILLABLE, reason="login_wall")

        submit_state = _install_submit_detector(context, page)

        if _dismiss_consent_banner(page):
            print("  dismissed consent banner", flush=True)
            page.wait_for_timeout(800)

        _think_pause(page, _PAGE_THINK_SECONDS, "page-load (LLM drafting)")

        # Iterative fill — many ATS forms (React-based: Greenhouse, Softgarden,
        # Lever) reveal conditional fields after earlier ones are filled
        # (country → state, file upload → autoparsed details) AND re-render
        # previously-filled controls back to empty. A single enumerate-then-fill
        # pass loses both classes. Loop: enumerate → LLM → fill → wait for
        # re-renders → re-enumerate. Cap at _MAX_ROUNDS to stop runaways.
        seen_field_ids: set[str] = set()
        total_applied = 0
        total_actions = 0
        advances = 0
        round_n = 0
        cv_attached = False  # attach the CV once — some ATSes re-render the file
        # input each round (new id), which would otherwise re-upload it.

        for round_n in range(1, _MAX_ROUNDS + 1):
            fields = _enumerate_fields(page)
            if round_n == 1:
                print(f"Round 1: enumerated {len(fields)} field(s)", flush=True)
                if not fields:
                    print(
                        "No fillable form fields detected after walking apply CTAs. "
                        "The page may be a login wall, an account-creation step, "
                        "or a non-standard widget. Flagging for manual apply.",
                        flush=True,
                    )
                    return ApplyResult(ApplyOutcome.NOT_FILLABLE, reason="login_wall")
                targets = fields
            else:
                targets = _select_round_targets(fields, seen_field_ids)
                print(
                    f"Round {round_n}: enumerated {len(fields)} field(s), "
                    f"targeting {len(targets)} (new or now-empty)",
                    flush=True,
                )
                if not targets:
                    # Nothing left on this page — try advancing to the next step
                    # of a multi-page form (safe-allowlisted; never submits).
                    if advances < _MAX_PAGE_ADVANCES and _advance_to_next_step(page):
                        advances += 1
                        print(f"  advanced to next step (#{advances})", flush=True)
                        _assert_not_easy_apply(page)  # a step may route to Easy Apply
                        # A login/register can appear mid-flow (e.g. join.com asks
                        # for a password once the email is recognised). Don't stall
                        # on it — flag for manual apply.
                        if _has_password_field(page):
                            print("  hit a login mid-flow (password field) — flagging for manual apply.", flush=True)
                            return ApplyResult(ApplyOutcome.NOT_FILLABLE, reason="login_wall")
                        continue
                    break

            try:
                actions = _ask_llm_for_actions(
                    fields=targets,
                    cover_letter=proposal,
                    adapted_cv=adapted_cv_md,
                    listing_title=listing_title,
                    listing_description=listing_description,
                )
            except Exception as e:
                print(f"LLM mapping failed in round {round_n} ({e}); aborting round loop", flush=True)
                break

            seen_field_ids.update(str(f["id"]) for f in targets if f.get("id"))
            total_actions += len(actions)
            # Selects before types before attach (phone-country before number; CV last).
            actions.sort(key=lambda a: _ACTION_PRIORITY.get((a.get("action") or "").lower(), 1))

            print(f"Round {round_n}: LLM produced {len(actions)} action(s)", flush=True)
            for action in actions:
                act = (action.get("action") or "").lower()
                if act == "attach" and cv_attached:
                    print(f"  [SKIP] {action.get('selector', '?')}  action=attach  CV already attached", flush=True)
                    continue
                _think_pause(page, _FIELD_THINK_SECONDS, f"field {action.get('selector', '?')}")
                ok, note = _apply_action(page, action, cv_pdf_path, proposal, cover_letter_pdf_path)
                label_hint = action.get("selector", "?")
                print(f"  [{'OK' if ok else 'SKIP'}] {label_hint}  action={action.get('action')}  {note}", flush=True)
                if ok and act != "skip":
                    total_applied += 1
                if ok and act == "attach":
                    cv_attached = True

            # Wait for the page to render any conditional fields revealed by
            # the fills (or to surface re-renders that cleared a previous fill).
            page.wait_for_timeout(_INTER_ROUND_WAIT_MS)

        print(
            f"Filled {total_applied}/{total_actions} fields across {round_n} round(s). "
            "Review the form, fix anything the LLM skipped, then click Submit yourself.",
            flush=True,
        )
        return _await_user_submit(page, submit_state)
    finally:
        browser.close()


# --- CLI ---------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auto-fill any external ATS via CDP-attached Chrome.")
    parser.add_argument("--ats-url", required=True, help="Direct URL of the employer's apply page")
    parser.add_argument("--proposal-file", required=True, help="Path to text file with cover letter / proposal")
    parser.add_argument("--cv-pdf-file", default=None, help="Path to CV PDF (attached when a file input is detected)")
    parser.add_argument("--cv-md-file", required=True, help="Path to adapted CV markdown (LLM context)")
    parser.add_argument("--listing-title", required=True, help="Listing title")
    parser.add_argument("--listing-desc-file", required=True, help="Path to listing description text")
    args = parser.parse_args(argv)

    proposal = Path(args.proposal_file).read_text(encoding="utf-8")
    cv_md = Path(args.cv_md_file).read_text(encoding="utf-8")
    listing_desc = Path(args.listing_desc_file).read_text(encoding="utf-8")
    cv_pdf = Path(args.cv_pdf_file) if args.cv_pdf_file else None
    apply(
        ats_url=args.ats_url,
        proposal=proposal,
        cv_pdf_path=cv_pdf,
        listing_title=args.listing_title,
        listing_description=listing_desc,
        adapted_cv_md=cv_md,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

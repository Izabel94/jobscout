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
import os
import random
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from jobscout.config_loader import load_profile
from jobscout.llm import LLMJSONError, call_json

_PAGE_THINK_SECONDS = (10.0, 18.0)
_FIELD_THINK_SECONDS = (0.6, 1.8)

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
  let n = 0;
  const mark = (el) => {
    const id = `__ats_${n++}`;
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


def _candidate_context(profile: dict[str, Any]) -> dict[str, str]:
    contact = profile.get("candidate_contact") or {}
    sensitive = profile.get("sensitive_field_defaults") or {}
    languages = profile.get("candidate_languages") or {}
    sens_lines = (
        "\n".join(f"  - {k}: {v}" for k, v in sensitive.items())
        if sensitive
        else "  (none configured)"
    )
    lang_lines = (
        "\n".join(f"  - {lang}: {level}" for lang, level in languages.items())
        if languages
        else "  (none configured)"
    )
    return {
        "candidate_name": str(profile.get("name", "")),
        "candidate_email": contact.get("email", ""),
        "candidate_phone": contact.get("phone", ""),
        "candidate_location": contact.get("location", "Hamburg, Germany"),
        "candidate_linkedin": contact.get("linkedin", ""),
        "candidate_portfolio": contact.get("portfolio", ""),
        "years_experience": str(contact.get("years_experience", "")),
        "available_hours_per_week": str(profile.get("max_hours_per_week", "")),
        "target_rate_eur_hr": str(profile.get("target_rate_floor_eur_hr", "")),
        "target_rate_usd_hr": str(profile.get("target_rate_floor_usd_hr", "")),
        "work_authorization": contact.get("work_authorization", ""),
        "sensitive_defaults": sens_lines,
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
    profile = load_profile()
    ctx = _candidate_context(profile)
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
    model = profile["model_draft"]
    result = call_json(
        model=model,
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
    page: Page, action: dict[str, Any], cv_pdf_path: Path | None, cover_letter: str
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
    """Return href of first visible Apply / Jetzt bewerben anchor or button."""
    return page.evaluate(
        """(keywords) => {
          const candidates = Array.from(document.querySelectorAll('a, button, [role="button"]'));
          for (const el of candidates) {
            const text = ((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase().trim();
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


def _walk_to_form(context: BrowserContext, page: Page) -> Page:
    """Follow Apply CTAs until the page exposes form fields, up to _MAX_APPLY_HOPS."""
    for hop in range(_MAX_APPLY_HOPS):
        fields = _enumerate_fields(page)
        if fields:
            return page
        cta_href = _find_apply_cta(page)
        if not cta_href:
            return page
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
    return page


def _find_or_open_target_page(context: BrowserContext, ats_url: str) -> Page:
    """Reuse an existing tab on the same host (LinkedIn flow lands here pre-opened) or open new."""
    target_host = (urlparse(ats_url).hostname or "").lower()
    for pg in context.pages:
        try:
            host = (urlparse(pg.url).hostname or "").lower()
        except Exception:
            continue
        if host and host == target_host:
            return pg
    page = context.new_page()
    page.goto(ats_url, wait_until="domcontentloaded", timeout=30_000)
    return page


# --- Public API --------------------------------------------------------------


def apply(
    *,
    ats_url: str,
    proposal: str,
    cv_pdf_path: Path | None,
    listing_title: str,
    listing_description: str,
    adapted_cv_md: str,
) -> None:
    cdp_url = os.environ.get("JOBSCOUT_CDP_URL")
    if not cdp_url:
        print(
            "JOBSCOUT_CDP_URL not set. Launch the CDP Chrome first:\n"
            "    bash scripts/chrome-cdp.sh\n"
            "then re-run with JOBSCOUT_CDP_URL=http://localhost:9222",
            flush=True,
        )
        sys.exit(2)
    with sync_playwright() as p:
        _run(p, cdp_url, ats_url, proposal, cv_pdf_path, listing_title, listing_description, adapted_cv_md)


def _run(
    p: Playwright,
    cdp_url: str,
    ats_url: str,
    proposal: str,
    cv_pdf_path: Path | None,
    listing_title: str,
    listing_description: str,
    adapted_cv_md: str,
) -> None:
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

        if _dismiss_consent_banner(page):
            print("  dismissed consent banner", flush=True)
            page.wait_for_timeout(800)

        _think_pause(page, _PAGE_THINK_SECONDS, "page-load (LLM drafting)")

        fields = _enumerate_fields(page)
        print(f"Enumerated {len(fields)} field(s)", flush=True)
        if not fields:
            print(
                "No fillable form fields detected after walking apply CTAs. "
                "The page may be a login wall, an account-creation step, "
                "or a non-standard widget. Inspect manually.",
                flush=True,
            )
            page.wait_for_event("close", timeout=0)
            return

        try:
            actions = _ask_llm_for_actions(
                fields=fields,
                cover_letter=proposal,
                adapted_cv=adapted_cv_md,
                listing_title=listing_title,
                listing_description=listing_description,
            )
        except Exception as e:
            print(f"LLM mapping failed ({e}); leaving form blank for manual fill", flush=True)
            page.wait_for_event("close", timeout=0)
            return

        print(f"LLM produced {len(actions)} action(s)", flush=True)
        applied = 0
        for action in actions:
            _think_pause(page, _FIELD_THINK_SECONDS, f"field {action.get('selector', '?')}")
            ok, note = _apply_action(page, action, cv_pdf_path, proposal)
            label_hint = action.get("selector", "?")
            print(f"  [{'OK' if ok else 'SKIP'}] {label_hint}  action={action.get('action')}  {note}", flush=True)
            if ok and (action.get("action") or "").lower() != "skip":
                applied += 1

        print(
            f"Filled {applied}/{len(actions)} fields. Review the form, fix anything the "
            "LLM skipped, then click Submit yourself.",
            flush=True,
        )
        page.wait_for_event("close", timeout=0)
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

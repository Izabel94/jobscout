"""One-shot script: scrape an end user's LinkedIn profile and upsert the
structured result to Supabase's profiles row.

Attaches via CDP to a Chrome the operator already launched via
`bash scripts/chrome-cdp.sh` and signed into LinkedIn in. Google's anti-
automation rejects Playwright-launched browsers; attaching to a real,
user-launched Chrome with an existing session avoids that entirely.

Usage:
    bash scripts/chrome-cdp.sh       # in one terminal, sign into LinkedIn
    make bootstrap-profile LINKEDIN_URL=https://www.linkedin.com/in/<the-user>/
"""

from __future__ import annotations

import json
import os
import sys

from playwright.sync_api import sync_playwright

import json
import re

from jobscout.db import upsert_profile
from jobscout.llm import call_text

CDP_URL = os.environ.get("JOBSCOUT_CDP_URL", "http://localhost:9222")

EXTRACT_PROMPT = """Below is the visible text of a LinkedIn profile page.
Extract the candidate's information as JSON matching this schema. Return
ONLY the JSON, no markdown fences.

Schema:
{
  "full_name": "string",
  "headline": "string",
  "location": "string",
  "summary": "string (the About section)",
  "skills": ["string", ...],
  "positions": [
    {"title": "string", "company": "string", "start": "YYYY-MM or empty",
     "end": "YYYY-MM or 'present' or empty", "description": "string"}
  ],
  "education": [{"degree": "string", "school": "string", "year": "string"}],
  "languages": {"German": "C1", "English": "C2", ...}
}

If a section isn't visible, return an empty string / empty list / empty
dict for that field. Do not invent.

Profile text:
{{page_text}}
"""


def _parse_lenient_json(raw: str) -> dict:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
    s = s.strip()
    # Strip trailing commas before `}` or `]` — the most common Gemini glitch.
    s = re.sub(r",(\s*[}\]])", r"\1", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # If the output was truncated mid-object, find the last balanced `}` and try.
    last_close = s.rfind("}")
    if last_close > 0:
        candidate = s[: last_close + 1]
        candidate = re.sub(r",(\s*[}\]])", r"\1", candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    raise RuntimeError(f"Could not parse LLM JSON. Raw:\n{raw[:2000]}")


def _scrape_text(linkedin_url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        try:
            page.goto(linkedin_url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3_000)
            if "/login" in page.url or "/checkpoint" in page.url or "authwall" in page.url:
                raise RuntimeError(
                    f"Hit LinkedIn authwall at {page.url!r}. "
                    "Sign into LinkedIn in the chrome-cdp.sh Chrome window and re-run."
                )
            text = page.evaluate("() => document.body.innerText")
            return str(text)
        finally:
            page.close()
            browser.close()


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("https://"):
        print(__doc__, file=sys.stderr)
        return 2
    linkedin_url = sys.argv[1].rstrip("/")
    print(f"Connecting to CDP Chrome at {CDP_URL} ...", flush=True)
    print(f"Scraping {linkedin_url} ...", flush=True)
    text = _scrape_text(linkedin_url)
    print(f"Got {len(text)} chars; extracting via LLM ...", flush=True)
    raw = call_text(
        model="gemini-2.5-flash",
        system="You extract structured candidate data from LinkedIn profile text. Return ONLY valid JSON, no markdown fences, no trailing commas.",
        user=EXTRACT_PROMPT.replace("{{page_text}}", text[:25_000]),
        max_tokens=8000,
    )
    extracted = _parse_lenient_json(raw)
    print("LLM result (truncated):")
    print(json.dumps(extracted, indent=2, ensure_ascii=False)[:800])
    if not extracted.get("full_name"):
        print("ERROR: LLM didn't extract a name — check page text", file=sys.stderr)
        return 1
    payload = {
        "linkedin_url": linkedin_url,
        "full_name": extracted.get("full_name") or "",
        "headline": extracted.get("headline") or "",
        "location": extracted.get("location") or "",
        "summary": extracted.get("summary") or "",
        "skills": extracted.get("skills") or [],
        "positions": extracted.get("positions") or [],
        "education": extracted.get("education") or [],
        "languages": extracted.get("languages") or {},
    }
    upsert_profile(payload)
    print(f"Upserted profile for {payload['full_name']!r}.", flush=True)
    print(f"Set JOBSCOUT_PROFILE_LINKEDIN_URL={linkedin_url} in .env", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""One-shot script: scrape an end user's LinkedIn profile and upsert the
structured result to Supabase's profiles row.

Operator runs this once per new end user. First run prompts for LinkedIn
login in a visible Chromium window; subsequent runs reuse the session.

Usage:
    poetry run dotenv run -- python scripts/bootstrap_profile_from_linkedin.py \\
        https://www.linkedin.com/in/<the-user>/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from jobscout.db import upsert_profile
from jobscout.llm import call_json

PROFILE_DIR = Path.home() / ".cache" / "jobscout" / "linkedin-profile"

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


def _scrape_text(linkedin_url: str) -> str:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30_000)
        if "/login" in page.url or "/checkpoint" in page.url:
            print("Operator: log in to LinkedIn in the opened window, then press Enter here.", flush=True)
            input()
        page.goto(linkedin_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(3_000)
        text = page.evaluate("() => document.body.innerText")
        context.close()
        return str(text)


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("https://"):
        print(__doc__, file=sys.stderr)
        return 2
    linkedin_url = sys.argv[1].rstrip("/")
    print(f"Scraping {linkedin_url} ...", flush=True)
    text = _scrape_text(linkedin_url)
    print(f"Got {len(text)} chars; extracting via LLM ...", flush=True)
    extracted = call_json(
        model="gemini-2.5-flash",
        system="You extract structured candidate data from LinkedIn profile text.",
        user=EXTRACT_PROMPT.replace("{{page_text}}", text[:25_000]),
        max_tokens=4000,
    )
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

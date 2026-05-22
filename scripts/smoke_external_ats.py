"""Manual end-to-end smoke for the apply pipeline.

Prereqs:
  bash scripts/chrome-cdp.sh                 # window 1
  export JOBSCOUT_CDP_URL=http://localhost:9222
  export JOBSCOUT_PROFILE_LINKEDIN_URL=https://www.linkedin.com/in/julian-engelke-449211209/

Then in window 2:
  poetry run python scripts/smoke_external_ats.py

Pick a public Greenhouse demo job (e.g. boards.greenhouse.io/embed/job_app?token=...).
Inspect the filled fields manually, then CLOSE the tab — do not submit.
"""

from __future__ import annotations

import sys
from pathlib import Path

from jobscout.apply import external_ats

DEMO_ATS_URL = "https://boards.greenhouse.io/greenhouse/jobs/4030001005"  # public demo
PROPOSAL = "Hi — this is a smoke test of the jobscout apply pipeline. Please disregard."


def main() -> int:
    cv_pdf = Path("/tmp/jobscout-smoke-cv.pdf")
    if not cv_pdf.exists():
        print(f"Place a sample CV PDF at {cv_pdf} before running.")
        return 2

    external_ats.apply(
        ats_url=DEMO_ATS_URL,
        proposal=PROPOSAL,
        cv_pdf_path=cv_pdf,
        listing_title="Smoke Test Engineer",
        listing_description="Diagnostic listing — do not apply for real.",
        adapted_cv_md="# Julian Engelke\n\nHamburg — smoke test\n",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

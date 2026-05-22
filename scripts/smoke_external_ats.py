"""Manual end-to-end smoke for the apply pipeline.

Prereqs:
  bash scripts/chrome-cdp.sh                 # window 1
  export JOBSCOUT_CDP_URL=http://localhost:9222
  export JOBSCOUT_PROFILE_LINKEDIN_URL=https://www.linkedin.com/in/julian-engelke-449211209/

Then in window 2:
  poetry run python scripts/smoke_external_ats.py

Smoke target is a real public Greenhouse application form (verified live
2026-05-22 via Playwright MCP). Inspect the filled fields manually, then
CLOSE the tab — do not submit.
"""

from __future__ import annotations

import sys
from pathlib import Path

# pyproject has `package-mode = false`, so jobscout isn't installed; put the
# repo root on sys.path so this script works when launched as `python scripts/...`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobscout.apply import external_ats  # noqa: E402

# Greenhouse's own public application for Forward Deployed Engineer (Ontario).
# Has ~20 fields covering text/email/select/file/textarea/checkbox — a thorough
# enumeration test. The role location (Ontario) is irrelevant for smoke purposes.
DEMO_ATS_URL = "https://job-boards.greenhouse.io/greenhouse/jobs/7891787?gh_jid=7891787"
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

"""Generates a tailored cover letter and adapted CV for one Listing."""

import logging
import re
from pathlib import Path

from jobscout.config_loader import load_cv_markdown, load_profile, render_candidate_block
from jobscout.db import list_by_status, update_listing_status, write_draft
from jobscout.llm import LLMProviderError, call_text
from jobscout.models import Draft, Listing, ListingStatus

log = logging.getLogger("draft")

_MODEL_DRAFT = "gemini-2.5-flash"  # free-tier; 2.5-pro has zero free quota
# CV adaptation is a literal fact-preserving edit — use the deterministic
# non-thinking model. 2.5-flash's variance intermittently dropped trailing
# entries/years, failing _verify_cv_facts.
_MODEL_CV = "gemini-3.1-flash-lite"
_PROMPT_VERSIONS = {"draft_proposal": "v1", "draft_cv": "v1"}  # spec decision

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"
_PROMPT_PROP = (_PROMPTS_DIR / "draft_proposal.v1.md").read_text(encoding="utf-8")
_PROMPT_CV = (_PROMPTS_DIR / "draft_cv.v1.md").read_text(encoding="utf-8")


def _extract_entry_headers(cv_md: str) -> list[str]:
    return [line[4:].strip() for line in cv_md.splitlines() if line.startswith("### ")]


# Compound German names like "Müller-Heinemann" or "von Hagen-Schmidt" — up to 3 follow-on capitalized tokens.
_CONTACT_RE = re.compile(
    r"Ansprechpartner[:\s]+([A-ZÄÖÜ][a-zäöüßA-ZÄÖÜ\-]+(?:\s+[A-ZÄÖÜ][a-zäöüßA-ZÄÖÜ\-]+){1,3})",
)


def _extract_contact_name(text: str) -> str:
    match = _CONTACT_RE.search(text or "")
    return match.group(1).strip() if match else ""


def _verify_cv_facts(cv_base_md: str, adapted_md: str) -> list[str]:
    """Check every `### ` header and every 4-digit year from the base survives in the adapted output."""
    violations: list[str] = []
    for header in _extract_entry_headers(cv_base_md):
        if header not in adapted_md:
            violations.append(f"missing entry header: {header}")
    year_re = re.compile(r"\b(?:19|20)\d{2}\b")
    base_years = set(year_re.findall(cv_base_md))
    adapted_years = set(year_re.findall(adapted_md))
    dropped = base_years - adapted_years
    if dropped:
        violations.append(f"dropped years: {sorted(dropped)}")
    return violations


def _build_proposal_prompt(profile: dict, listing: Listing, language: str, contact_name: str) -> str:
    notes = (profile.get("scorer_notes") or "").strip()
    user_pref_block = ""
    if notes:
        user_pref_block = (
            "# User preferences (mandatory — apply when drafting)\n\n"
            f"{notes}\n\n"
        )
    return (
        _PROMPT_PROP.replace("{{candidate_block}}", render_candidate_block(profile))
        .replace("{{user_pref_block}}", user_pref_block)
        .replace("{{candidate_name}}", str(profile.get("full_name") or ""))
        .replace("{{title}}", listing.title)
        .replace("{{description}}", (listing.description or "")[:4000])
        .replace("{{language}}", language)
        .replace("{{contact_name}}", contact_name)
    )


def draft_one(listing: Listing) -> Draft:
    profile = load_profile()
    cv_language = listing.language or "de"
    cv_base_md = load_cv_markdown(cv_language)

    contact_name = _extract_contact_name(listing.description or "")

    rendered_prop = _build_proposal_prompt(profile, listing, cv_language, contact_name)
    rendered_cv = _PROMPT_CV.replace("{{cv_base_markdown}}", cv_base_md).replace(
        "{{listing_full}}", f"{listing.title}\n\n{listing.description or ''}"
    )

    # Cover letter: 2.5-flash for quality, but its free tier is ~20 req/day — on
    # quota exhaustion fall back to flash-lite so drafting never hard-fails.
    # Headroom leaves room for the thinking model's hidden reasoning.
    try:
        body = call_text(model=_MODEL_DRAFT, system="You write cover letters.", user=rendered_prop, max_tokens=3000)
    except LLMProviderError:
        body = call_text(model=_MODEL_CV, system="You write cover letters.", user=rendered_prop, max_tokens=3000)
    cv_md = call_text(
        model=_MODEL_CV,
        system="You preserve every fact exactly and make only surgical, listing-aligned edits.",
        user=rendered_cv,
        max_tokens=10000,
    )

    violations = _verify_cv_facts(cv_base_md, cv_md)
    if violations:
        raise ValueError(f"CV adaptation broke fact preservation: {violations}")
    if listing.id is None:
        raise ValueError("listing.id is None — cannot persist draft")

    draft = Draft(
        listing_id=listing.id,
        language=cv_language,
        body=body,
        adapted_cv=cv_md,
        model=_MODEL_DRAFT,
        prompt_version=f"prop:{_PROMPT_VERSIONS['draft_proposal']};cv:{_PROMPT_VERSIONS['draft_cv']}",
    )
    write_draft(draft)
    update_listing_status(listing.id, ListingStatus.DRAFTED)
    return draft


def main() -> None:
    """Draft every scored listing that doesn't yet have a draft.

    Driven by the daily cron after score.py. Cron order is
    discover → filter → score → draft.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    rows = list_by_status(ListingStatus.SCORED)
    log.info("drafting %d scored listings with %s", len(rows), _MODEL_DRAFT)
    for row in rows:
        listing_id = str(row["id"])
        try:
            draft_one(Listing.model_validate(row))
        except Exception as exc:  # noqa: BLE001 — survive the loop
            log.error("draft failed for %s: %s", listing_id, exc)


if __name__ == "__main__":
    main()

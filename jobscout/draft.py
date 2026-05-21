"""Generates a tailored proposal and adapted CV for one Listing."""

import re
from pathlib import Path
from typing import Any

from jobscout.config_loader import load_cv_markdown, load_profile
from jobscout.db import update_listing_status, write_draft
from jobscout.llm import call_text
from jobscout.models import Draft, Listing, ListingStatus

_MODEL_DRAFT = "gemini-2.5-flash"  # spec decision
_PROMPT_VERSIONS = {"draft_proposal": "v1", "draft_cv": "v1"}  # spec decision

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"
_PROMPT_PROP = (_PROMPTS_DIR / "draft_proposal.v1.md").read_text(encoding="utf-8")
_PROMPT_CV = (_PROMPTS_DIR / "draft_cv.v1.md").read_text(encoding="utf-8")


def _profile_blurb(profile: dict[str, Any]) -> str:
    skills = ", ".join((profile.get("required_skill_keywords") or [])[:10])
    name = profile.get("full_name") or ""
    return f"{name} — AI Engineer (Hamburg). Stack: {skills}"


def _case_studies(profile: dict[str, Any]) -> str:
    summaries = profile.get("anchor_summaries") or []
    return "\n\n".join(f"- {c['title']}: {c['summary']}" for c in summaries)


def _extract_entry_headers(cv_md: str) -> list[str]:
    """Each `### ` header marks an employer/institution — the unit we must keep intact during adaptation."""
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


def draft_one(listing: Listing) -> Draft:
    profile = load_profile()
    cv_language = listing.language or "en"
    cv_base_md = load_cv_markdown(cv_language)

    contact_name = _extract_contact_name(listing.description or "")

    rendered_prop = (
        _PROMPT_PROP.replace("{{profile_blurb}}", _profile_blurb(profile))
        .replace("{{candidate_name}}", str(profile.get("full_name") or ""))
        .replace("{{anchor_case_studies}}", _case_studies(profile))
        .replace("{{title}}", listing.title)
        .replace("{{description}}", (listing.description or "")[:4000])
        .replace("{{language}}", cv_language)
        .replace("{{contact_name}}", contact_name)
    )
    rendered_cv = _PROMPT_CV.replace("{{cv_base_markdown}}", cv_base_md).replace(
        "{{listing_full}}", f"{listing.title}\n\n{listing.description or ''}"
    )

    body = call_text(model=_MODEL_DRAFT, system="You write proposals.", user=rendered_prop, max_tokens=800)
    cv_md = call_text(
        model=_MODEL_DRAFT,
        system="You preserve every fact exactly and make only surgical, listing-aligned edits.",
        user=rendered_cv,
        max_tokens=6000,
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

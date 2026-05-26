"""Profile + spam-rules loader.

Profile is the single `profiles` row from Supabase, keyed on the
`JOBSCOUT_PROFILE_LINKEDIN_URL` env var. Cached per-process.

Sidegig read this from config/profile.yaml — that file was deleted in the
fork. End user edits fields via the Streamlit Settings tab (Phase 3 plan),
which round-trips through db.upsert_profile().
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import yaml

from jobscout.db import get_profile

_CFG_DIR = Path(__file__).resolve().parent.parent / "config"


def _profile_linkedin_url() -> str:
    url = os.environ.get("JOBSCOUT_PROFILE_LINKEDIN_URL")
    if not url:
        raise RuntimeError(
            "JOBSCOUT_PROFILE_LINKEDIN_URL not set. Run scripts/bootstrap_profile_from_linkedin.py "
            "first, then set this env var to the user's LinkedIn URL."
        )
    return url


@lru_cache(maxsize=1)
def _load_profile_cached() -> dict[str, Any]:
    url = _profile_linkedin_url()
    p = get_profile(url)
    if p is None:
        raise RuntimeError(
            f"No profiles row found for linkedin_url={url!r}. "
            "Run scripts/bootstrap_profile_from_linkedin.py to populate."
        )
    return p


def load_profile() -> dict[str, Any]:
    return _load_profile_cached()


def clear_profile_cache() -> None:
    _load_profile_cached.cache_clear()


def render_candidate_block(profile: dict[str, Any]) -> str:
    """Render the profile row as a markdown block the LLM can read.

    Used by score + draft prompts so the candidate description is sourced
    from the live Supabase profile, not hardcoded in the prompt template.
    """
    lines: list[str] = []
    if name := profile.get("full_name"):
        lines.append(f"**Name:** {name}")
    if headline := profile.get("headline"):
        lines.append(f"**Current role:** {headline}")
    if location := profile.get("location"):
        lines.append(f"**Location:** {location}")
    summary = (profile.get("summary") or "").strip()
    if summary:
        lines.append("")
        lines.append(f"**Summary:** {summary}")
    skills = profile.get("skills") or []
    if skills:
        lines.append("")
        lines.append(f"**Skills:** {', '.join(skills)}")
    positions = profile.get("positions") or []
    if positions:
        lines.append("")
        lines.append("**Recent experience:**")
        for p in positions[:5]:
            title = (p.get("title") or "").strip()
            company = (p.get("company") or "").strip()
            start = (p.get("start") or "").strip()
            end = (p.get("end") or "").strip()
            dates = f"{start} – {end}" if start or end else ""
            header = f"- **{title}** at {company}" if title and company else f"- {title or company}"
            if dates:
                header = f"{header} ({dates})"
            lines.append(header)
            desc = (p.get("description") or "").strip()
            if desc:
                short = desc[:500].strip()
                indented = "\n".join(f"  {ln}" for ln in short.splitlines() if ln.strip())
                lines.append(indented)
    education = profile.get("education") or []
    if education:
        lines.append("")
        lines.append("**Education:**")
        for e in education:
            school = (e.get("school") or "").strip()
            degree = (e.get("degree") or "").strip()
            year = (e.get("year") or "").strip()
            bits = [degree, school, f"({year})" if year else ""]
            lines.append("- " + " · ".join(b for b in bits if b))
    return "\n".join(lines).strip()


@lru_cache(maxsize=1)
def load_spam_rules() -> dict[str, Any]:
    with open(_CFG_DIR / "spam_rules.yaml") as f:
        return cast(dict[str, Any], yaml.safe_load(f))


def synthesize_cv_markdown_from_profile(profile: dict[str, Any]) -> str:
    """Build a CV-shaped markdown from the structured profiles row (LinkedIn scrape).

    Used as the final fallback in `load_cv_markdown` when neither an env-var
    override, nor a `config/cv_base_*.md` file, nor `profile.cv_markdown` is
    available. Matches the `### Company | Location` + `**Role** | *Dates*`
    convention `cv_render.py` and `config/templates/cv.html.j2` expect.
    """
    name = profile.get("full_name") or "Candidate"
    email = profile.get("email") or ""
    phone = profile.get("phone") or ""
    linkedin = profile.get("linkedin_url") or ""
    location = profile.get("location") or ""
    headline = profile.get("headline") or ""
    summary = (profile.get("summary") or "").strip()
    skills = profile.get("skills") or []
    positions = profile.get("positions") or []
    education = profile.get("education") or []

    contact_bits = [b for b in (email, phone, f"<{linkedin}>" if linkedin else "") if b]
    lines: list[str] = [f"# {name}", "", " · ".join(contact_bits), ""]
    if headline:
        lines += [f"**{headline}**", ""]
    if summary:
        lines += ["## Summary", "", summary, ""]
    if positions:
        lines += ["## Experience", ""]
        for p in positions:
            company = (p.get("company") or "").strip()
            title = (p.get("title") or "").strip()
            start = (p.get("start") or "").strip()
            end = (p.get("end") or "").strip()
            dates = f"{start} – {end}" if start or end else ""
            desc = (p.get("description") or "").strip()
            if location and company:
                lines += [f"### {company} | {location}"]
            elif company:
                lines += [f"### {company}"]
            lines += [""]
            if title and dates:
                lines += [f"**{title}** | *{dates}*"]
            elif title:
                lines += [f"**{title}**"]
            lines += [""]
            if desc:
                lines += [desc, ""]
    if education:
        lines += ["## Education", ""]
        for e in education:
            school = (e.get("school") or "").strip()
            degree = (e.get("degree") or "").strip()
            year = (e.get("year") or "").strip()
            if school:
                lines += [f"### {school}"]
            lines += [""]
            if degree and year:
                lines += [f"**{degree}** | *{year}*"]
            elif degree:
                lines += [f"**{degree}**"]
            lines += [""]
    if skills:
        lines += ["## Skills", "", ", ".join(skills), ""]
    return "\n".join(lines)


@lru_cache(maxsize=2)
def load_cv_markdown(language: str) -> str:
    """CV markdown by language. Resolution order:
    env var → config file → profile.cv_markdown → synthesize from profile fields.

    The synthesis fallback exists so the pipeline works against a LinkedIn-only
    profile (no CV uploaded yet) — typical for the first weeks of a new end user.
    Once the operator runs bootstrap_profile_from_cv.py, profile.cv_markdown
    is set and takes precedence.
    """
    is_de = language.lower().startswith("de")
    env_key = "CV_BASE_DE" if is_de else "CV_BASE_EN"
    if from_env := os.environ.get(env_key):
        return from_env
    path = _CFG_DIR / ("cv_base_de.md" if is_de else "cv_base_en.md")
    if path.exists():
        return path.read_text(encoding="utf-8")
    profile = _load_profile_cached()
    if cv_md := (profile.get("cv_markdown") or "").strip():
        return cv_md
    return synthesize_cv_markdown_from_profile(profile)

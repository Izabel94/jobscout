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


@lru_cache(maxsize=1)
def load_spam_rules() -> dict[str, Any]:
    with open(_CFG_DIR / "spam_rules.yaml") as f:
        return cast(dict[str, Any], yaml.safe_load(f))


@lru_cache(maxsize=2)
def load_cv_markdown(language: str) -> str:
    """CV markdown by language. Env var wins over file."""
    is_de = language.lower().startswith("de")
    env_key = "CV_BASE_DE" if is_de else "CV_BASE_EN"
    if from_env := os.environ.get(env_key):
        return from_env
    path = _CFG_DIR / ("cv_base_de.md" if is_de else "cv_base_en.md")
    if path.exists():
        return path.read_text(encoding="utf-8")
    raise RuntimeError(f"CV markdown not found: set {env_key} or create {path}")

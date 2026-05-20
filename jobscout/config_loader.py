import os
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import yaml

_CFG_DIR = Path(__file__).resolve().parent.parent / "config"


@lru_cache(maxsize=1)
def load_profile() -> dict[str, Any]:
    with open(_CFG_DIR / "profile.yaml") as f:
        return cast(dict[str, Any], yaml.safe_load(f))


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


@lru_cache(maxsize=1)
def load_onboarding_seed() -> list[dict[str, Any]]:
    """Return the list under the `targets:` key in onboarding_seed.yaml."""
    with open(_CFG_DIR / "onboarding_seed.yaml") as f:
        data = cast(dict[str, Any], yaml.safe_load(f))
    return cast(list[dict[str, Any]], data["targets"])

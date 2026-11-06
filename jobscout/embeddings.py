"""Sentence-transformer embeddings + cosine similarity for Hard Filter 4.

The model (~80MB) is loaded lazily and cached for the process lifetime. The
profile embedding (built from anchor summaries + required skill keywords)
is also cached, so each listing only pays the per-text encode cost.
"""

from functools import lru_cache
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray
from sentence_transformers import SentenceTransformer

from jobscout.config_loader import load_profile

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    return SentenceTransformer(_MODEL_NAME)


@lru_cache(maxsize=1)
def _profile_embedding() -> NDArray[Any]:
    profile = load_profile()
    parts = [f"{c['title']}: {c['summary']}" for c in profile.get("anchor_summaries") or []]
    parts.append(", ".join(profile.get("required_skill_keywords") or []))
    return cast(NDArray[Any], _model().encode("\n\n".join(parts), normalize_embeddings=True))


@lru_cache(maxsize=1)
def _target_role_embeddings() -> NDArray[Any] | None:
    targets = [t for t in load_profile().get("required_skill_keywords") or [] if t.strip()]
    if not targets:
        return None
    return cast(NDArray[Any], _model().encode(targets, normalize_embeddings=True))


def cosine_to_profile(text: str) -> float:
    """Best similarity to the whole profile or to any single target role.

    The profile blend is dominated by past roles, so a career-change listing
    ('Account Manager' for a media consultant) scores low against it; matching
    each target role on its own keeps those listings."""
    embedding = cast(NDArray[Any], _model().encode(text, normalize_embeddings=True))
    best = float(np.dot(embedding, _profile_embedding()))
    targets = _target_role_embeddings()
    if targets is not None:
        best = max(best, float(np.max(targets @ embedding)))
    return best

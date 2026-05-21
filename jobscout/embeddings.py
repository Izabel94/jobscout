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


def cosine_to_profile(text: str) -> float:
    embedding = cast(NDArray[Any], _model().encode(text, normalize_embeddings=True))
    return float(np.dot(embedding, _profile_embedding()))

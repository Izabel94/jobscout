"""Provider-agnostic LLM wrapper.

Choose backend via env var `LLM_PROVIDER` (default `gemini`). Add a new provider
by writing a `_call_*` function with signature `(model, system, user, max_tokens) -> str`
and registering it in `_PROVIDERS`. The public `call_text` / `call_json` API is
identical regardless of backend.

Model names are hardcoded as module-level constants (`_MODEL_SCORE`, `_MODEL_DRAFT`)
in `score.py` and `draft.py`. When switching provider, swap those constants — no
profile-row change needed.
"""

from __future__ import annotations

import json
import os
import re
import time
from functools import lru_cache
from typing import Any, Protocol, cast


class LLMJSONError(ValueError):
    """Model returned invalid JSON."""


class LLMProviderError(RuntimeError):
    """Provider call failed after retries."""


class _ProviderFn(Protocol):
    def __call__(self, *, model: str, system: str, user: str, max_tokens: int) -> str: ...


def _call_gemini(*, model: str, system: str, user: str, max_tokens: int) -> str:
    client = _gemini_client()
    resp = client.models.generate_content(
        model=model,
        contents=user,
        config={
            "system_instruction": system,
            "max_output_tokens": max_tokens,
        },
    )
    return cast(str, getattr(resp, "text", "") or "")


_PROVIDERS: dict[str, _ProviderFn] = {
    "gemini": _call_gemini,
}


@lru_cache(maxsize=1)
def _gemini_client() -> Any:
    from google import genai

    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def _provider() -> _ProviderFn:
    # jobscout is gemini-only; any other LLM_PROVIDER value (including a stale
    # 'anthropic' inherited from sidegig config) resolves to gemini rather than
    # crashing on a missing SDK.
    return _PROVIDERS.get(_provider_name(), _call_gemini)


def _retryable_excs() -> tuple[type[BaseException], ...]:
    """Gemini exception classes to retry on (429 / RESOURCE_EXHAUSTED etc.)."""
    from google.genai import errors as genai_errors

    return (genai_errors.APIError,)


def _provider_name() -> str:
    return os.environ.get("LLM_PROVIDER", "gemini").lower()


_RATE_LIMIT_RETRY_DELAY_RE = re.compile(r"'retryDelay':\s*'(\d+)s'")
_ATTEMPTS_PER_MODEL = 3


def _rate_limit_wait_seconds(err: BaseException) -> float | None:
    """If the exception is a 429 / RESOURCE_EXHAUSTED, return how long the
    provider asked us to wait. We honor that delay verbatim — exponential
    backoff at 1-2-4s is useless against a per-minute quota."""
    msg = str(err)
    if "429" not in msg and "RESOURCE_EXHAUSTED" not in msg:
        return None
    m = _RATE_LIMIT_RETRY_DELAY_RE.search(msg)
    return float(m.group(1)) + 1.0 if m else 60.0


def _server_error_wait(err: BaseException, attempt: int) -> float | None:
    """Longer backoff for transient 5xx (notably Gemini's 503 'high demand').
    A demand spike outlasts the 1-2-4s default, so wait 4-8-16s (capped 30)."""
    msg = str(err)
    if not any(code in msg for code in ("503", "502", "500", "UNAVAILABLE")):
        return None
    return min(float(2**attempt) * 4.0, 30.0)


def _call_one_model(provider: _ProviderFn, *, model: str, system: str, user: str, max_tokens: int) -> str:
    """Call a single model, retrying transient errors. Raises LLMProviderError
    if every attempt fails."""
    last_err: BaseException | None = None
    for attempt in range(_ATTEMPTS_PER_MODEL):
        try:
            return provider(model=model, system=system, user=user, max_tokens=max_tokens)
        except _retryable_excs() as e:
            last_err = e
            if attempt == _ATTEMPTS_PER_MODEL - 1:
                break
            wait = _rate_limit_wait_seconds(e) or _server_error_wait(e, attempt) or float(2**attempt)
            time.sleep(wait)
    raise LLMProviderError(f"LLM call to {model} failed after {_ATTEMPTS_PER_MODEL} attempts: {last_err}") from last_err


def call_text(*, model: str, system: str, user: str, max_tokens: int = 2000, fallback_model: str | None = None) -> str:
    """Call the model with retries; on exhaustion, retry once on fallback_model.

    The fallback routes around a single overloaded model — e.g. when
    gemini-3.1-flash-lite 503s under load, salary/score fall back to
    gemini-2.5-flash so the daily run doesn't hard-fail."""
    provider = _provider()
    try:
        return _call_one_model(provider, model=model, system=system, user=user, max_tokens=max_tokens)
    except LLMProviderError:
        if not fallback_model:
            raise
        return _call_one_model(provider, model=fallback_model, system=system, user=user, max_tokens=max_tokens)


def call_json(
    *, model: str, system: str, user: str, max_tokens: int = 2000, fallback_model: str | None = None
) -> dict[str, Any]:
    raw = call_text(model=model, system=system, user=user, max_tokens=max_tokens, fallback_model=fallback_model)
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
    try:
        parsed = json.loads(s.strip())
    except json.JSONDecodeError as e:
        raise LLMJSONError(f"could not parse JSON: {e}\nraw:\n{raw}") from e
    return cast(dict[str, Any], parsed)

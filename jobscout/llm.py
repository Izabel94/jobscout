"""Provider-agnostic LLM wrapper.

Choose backend via env var `LLM_PROVIDER` (default `anthropic`). Add a new provider
by writing a `_call_*` function with signature `(model, system, user, max_tokens) -> str`
and registering it in `_PROVIDERS`. The public `call_text` / `call_json` API is
identical regardless of backend.

Model names live in `config/profile.yaml` (`model_score`, `model_draft`). When
switching provider, swap the model IDs there — no code change needed elsewhere.
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


def _call_anthropic(*, model: str, system: str, user: str, max_tokens: int) -> str:
    msg = _anthropic_client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return cast(str, getattr(msg.content[0], "text", ""))


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
    "anthropic": _call_anthropic,
    "gemini": _call_gemini,
}


@lru_cache(maxsize=1)
def _anthropic_client() -> Any:
    from anthropic import Anthropic

    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


@lru_cache(maxsize=1)
def _gemini_client() -> Any:
    from google import genai

    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def _provider() -> _ProviderFn:
    name = _provider_name()
    try:
        return _PROVIDERS[name]
    except KeyError as e:
        raise LLMProviderError(f"Unknown LLM_PROVIDER {name!r}; expected one of {sorted(_PROVIDERS)}") from e


def _retryable_excs() -> tuple[type[BaseException], ...]:
    """Provider-specific exception classes to retry on. `_provider()` runs first,
    so by the time we get here the provider name is known to be valid."""
    name = _provider_name()
    if name == "anthropic":
        from anthropic import APIError

        return (APIError,)
    from google.genai import errors as genai_errors

    return (genai_errors.APIError,)


def _provider_name() -> str:
    return os.environ.get("LLM_PROVIDER", "anthropic").lower()


_RATE_LIMIT_RETRY_DELAY_RE = re.compile(r"'retryDelay':\s*'(\d+)s'")


def _rate_limit_wait_seconds(err: BaseException) -> float | None:
    """If the exception is a 429 / RESOURCE_EXHAUSTED, return how long the
    provider asked us to wait. We honor that delay verbatim — exponential
    backoff at 1-2-4s is useless against a per-minute quota."""
    msg = str(err)
    if "429" not in msg and "RESOURCE_EXHAUSTED" not in msg:
        return None
    m = _RATE_LIMIT_RETRY_DELAY_RE.search(msg)
    return float(m.group(1)) + 1.0 if m else 60.0


def call_text(*, model: str, system: str, user: str, max_tokens: int = 2000) -> str:
    provider = _provider()
    retryable = _retryable_excs()
    last_err: BaseException | None = None
    for attempt in range(3):
        try:
            return provider(model=model, system=system, user=user, max_tokens=max_tokens)
        except retryable as e:
            last_err = e
            wait = _rate_limit_wait_seconds(e) or float(2**attempt)
            time.sleep(wait)
    raise LLMProviderError(f"LLM call failed after 3 attempts: {last_err}") from last_err


def call_json(*, model: str, system: str, user: str, max_tokens: int = 2000) -> dict[str, Any]:
    raw = call_text(model=model, system=system, user=user, max_tokens=max_tokens)
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

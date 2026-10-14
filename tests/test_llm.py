from unittest.mock import patch

import pytest

from jobscout.llm import LLMJSONError, call_json


@patch("jobscout.llm._provider")
def test_call_json_parses_valid_response(mock_provider):
    mock_provider.return_value = lambda *, model, system, user, max_tokens: ('{"score": 75, "rationale": "good fit"}')
    assert call_json(model="m", system="s", user="u") == {"score": 75, "rationale": "good fit"}


@patch("jobscout.llm._provider")
def test_call_json_raises_on_invalid_json(mock_provider):
    mock_provider.return_value = lambda *, model, system, user, max_tokens: "not json at all"
    with pytest.raises(LLMJSONError):
        call_json(model="m", system="s", user="u")


@patch("jobscout.llm._provider")
def test_call_json_strips_markdown_fence(mock_provider):
    mock_provider.return_value = lambda *, model, system, user, max_tokens: ('```json\n{"a": 1}\n```')
    assert call_json(model="m", system="s", user="u") == {"a": 1}


def test_any_provider_resolves_to_gemini(monkeypatch):
    # jobscout is gemini-only: a stale 'anthropic' or any unknown value must
    # resolve to the gemini provider, never import a missing SDK.
    from jobscout.llm import _call_gemini, _provider

    for value in ("anthropic", "bogus", "GEMINI"):
        monkeypatch.setenv("LLM_PROVIDER", value)
        assert _provider() is _call_gemini


# --- retry + model fallback on transient provider errors (Gemini 503) ---


class _FakeAPIError(Exception):
    """Stands in for google.genai APIError in tests."""


def _no_sleep_and_fake_retryable(monkeypatch):
    import jobscout.llm as llm

    monkeypatch.setattr(llm, "_retryable_excs", lambda: (_FakeAPIError,))
    monkeypatch.setattr(llm.time, "sleep", lambda *_a, **_k: None)


def test_call_text_retries_same_model_then_succeeds(monkeypatch):
    import jobscout.llm as llm

    _no_sleep_and_fake_retryable(monkeypatch)
    attempts = {"n": 0}

    def flaky(*, model, system, user, max_tokens):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise _FakeAPIError("503 UNAVAILABLE high demand")
        return "ok"

    monkeypatch.setattr(llm, "_provider", lambda: flaky)
    assert llm.call_text(model="m", system="s", user="u") == "ok"


def test_call_text_falls_back_to_other_model_on_server_error(monkeypatch):
    import jobscout.llm as llm

    _no_sleep_and_fake_retryable(monkeypatch)
    seen: list[str] = []

    def provider(*, model, system, user, max_tokens):
        seen.append(model)
        if model == "primary":
            raise _FakeAPIError("503 UNAVAILABLE high demand")
        return "ok-from-fallback"

    monkeypatch.setattr(llm, "_provider", lambda: provider)
    out = llm.call_text(model="primary", system="s", user="u", fallback_model="backup")
    assert out == "ok-from-fallback"
    assert "primary" in seen and "backup" in seen


def test_call_text_raises_when_primary_and_fallback_both_fail(monkeypatch):
    import jobscout.llm as llm

    _no_sleep_and_fake_retryable(monkeypatch)

    def always_503(*, model, system, user, max_tokens):
        raise _FakeAPIError("503 UNAVAILABLE")

    monkeypatch.setattr(llm, "_provider", lambda: always_503)
    with pytest.raises(llm.LLMProviderError):
        llm.call_text(model="primary", system="s", user="u", fallback_model="backup")


def test_call_json_passes_fallback_model(monkeypatch):
    import jobscout.llm as llm

    _no_sleep_and_fake_retryable(monkeypatch)

    def provider(*, model, system, user, max_tokens):
        if model == "primary":
            raise _FakeAPIError("503 UNAVAILABLE")
        return '{"ok": true}'

    monkeypatch.setattr(llm, "_provider", lambda: provider)
    assert llm.call_json(model="primary", system="s", user="u", fallback_model="backup") == {"ok": True}

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

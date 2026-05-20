from unittest.mock import patch

import pytest

from jobscout.llm import LLMJSONError, LLMProviderError, call_json, call_text


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


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bogus")
    with pytest.raises(LLMProviderError):
        call_text(model="m", system="s", user="u")

"""Tests for the live (non-mock) LLM client path.

These tests never call OpenRouter — ``litellm.completion`` is monkeypatched
to return a canned response. We assert the request shape (model, provider,
messages) and the response parsing.
"""

from types import SimpleNamespace

import pytest

from app.llm import client as client_mod
from app.llm.client import LLMClient, LLMError
from app.llm.system_prompt import SYSTEM_PROMPT


def _fake_completion_response(content: str):
    """Mimic the LiteLLM ``ModelResponse`` shape we read from."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@pytest.fixture
def captured_calls(monkeypatch):
    calls: list[dict] = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return _fake_completion_response(
            '{"message": "Bought 1 AAPL.", "trades": [{"ticker": "AAPL", '
            '"side": "buy", "quantity": 1}], "watchlist_changes": []}'
        )

    fake_litellm = SimpleNamespace(completion=fake_completion)
    monkeypatch.setitem(__import__("sys").modules, "litellm", fake_litellm)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    return calls


class TestLiveCall:
    def test_uses_model_and_cerebras_provider(self, captured_calls):
        c = LLMClient(mock=False)
        c.complete("buy one AAPL")
        assert len(captured_calls) == 1
        call = captured_calls[0]
        assert call["model"] == client_mod.MODEL
        assert call["extra_body"] == client_mod.PROVIDER_ROUTING
        assert call["reasoning_effort"] == "low"
        assert call["response_format"] is __import__(
            "app.llm.schema", fromlist=["LLMResponse"]
        ).LLMResponse

    def test_messages_include_system_prompt_and_history(self, captured_calls):
        c = LLMClient(mock=False)
        c.complete(
            "buy one AAPL",
            portfolio_context="Cash: $10,000\nPositions: none",
            history=[
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
        )
        msgs = captured_calls[0]["messages"]
        assert msgs[0]["role"] == "system"
        assert SYSTEM_PROMPT.strip()[:20] in msgs[0]["content"]
        assert msgs[1]["role"] == "system"
        assert "Cash: $10,000" in msgs[1]["content"]
        assert msgs[2] == {"role": "user", "content": "hi"}
        assert msgs[3] == {"role": "assistant", "content": "hello"}
        assert msgs[-1] == {"role": "user", "content": "buy one AAPL"}

    def test_skips_empty_or_invalid_history_turns(self, captured_calls):
        c = LLMClient(mock=False)
        c.complete(
            "go",
            history=[
                {"role": "system", "content": "ignored"},
                {"role": "user", "content": ""},
                {"role": "assistant", "content": "kept"},
            ],
        )
        msgs = captured_calls[0]["messages"]
        roles_contents = [(m["role"], m["content"]) for m in msgs]
        assert ("system", "ignored") not in roles_contents
        assert ("user", "") not in roles_contents
        assert ("assistant", "kept") in roles_contents

    def test_response_is_parsed_into_llm_response(self, captured_calls):
        c = LLMClient(mock=False)
        r = c.complete("buy one AAPL")
        assert r.message == "Bought 1 AAPL."
        assert len(r.trades) == 1
        assert r.trades[0].ticker == "AAPL"
        assert r.trades[0].quantity == 1

    def test_no_portfolio_context_skips_context_message(self, captured_calls):
        c = LLMClient(mock=False)
        c.complete("hello")
        msgs = captured_calls[0]["messages"]
        system_msgs = [m for m in msgs if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert "portfolio context" not in system_msgs[0]["content"].lower()


class TestLiveErrors:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        c = LLMClient(mock=False)
        with pytest.raises(LLMError, match="OPENROUTER_API_KEY"):
            c.complete("hi")

    def test_provider_exception_wrapped(self, monkeypatch):
        def boom(**_):
            raise RuntimeError("network down")

        monkeypatch.setitem(
            __import__("sys").modules, "litellm", SimpleNamespace(completion=boom)
        )
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        c = LLMClient(mock=False)
        with pytest.raises(LLMError, match="network down"):
            c.complete("hi")

    def test_invalid_json_response_wrapped(self, monkeypatch):
        def bad(**_):
            return _fake_completion_response("not json")

        monkeypatch.setitem(
            __import__("sys").modules, "litellm", SimpleNamespace(completion=bad)
        )
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        c = LLMClient(mock=False)
        with pytest.raises(LLMError, match="parse"):
            c.complete("hi")

    def test_unexpected_response_shape_wrapped(self, monkeypatch):
        def weird(**_):
            return SimpleNamespace(choices=[])

        monkeypatch.setitem(
            __import__("sys").modules, "litellm", SimpleNamespace(completion=weird)
        )
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        c = LLMClient(mock=False)
        with pytest.raises(LLMError):
            c.complete("hi")

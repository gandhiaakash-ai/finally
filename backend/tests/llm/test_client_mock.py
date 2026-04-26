"""Tests for LLM_MOCK deterministic mode."""

import pytest

from app.llm.client import LLMClient, get_llm_client, reset_llm_client


@pytest.fixture
def client():
    return LLMClient(mock=True)


class TestMockMode:
    def test_greeting(self, client):
        r = client.complete("Hello there")
        assert "FinAlly" in r.message
        assert r.trades == []
        assert r.watchlist_changes == []

    def test_portfolio_query(self, client):
        r = client.complete("What's my portfolio looking like?")
        assert "portfolio" in r.message.lower()
        assert r.trades == []

    def test_buy_trade(self, client):
        r = client.complete("Please buy 10 shares of AAPL")
        assert len(r.trades) == 1
        assert r.trades[0].ticker == "AAPL"
        assert r.trades[0].side == "buy"
        assert r.trades[0].quantity == 10

    def test_sell_trade_fractional(self, client):
        r = client.complete("sell 2.5 GOOGL")
        assert len(r.trades) == 1
        assert r.trades[0].side == "sell"
        assert r.trades[0].ticker == "GOOGL"
        assert r.trades[0].quantity == 2.5

    def test_watchlist_add(self, client):
        r = client.complete("add NVDA to my watchlist please")
        assert r.watchlist_changes[0].ticker == "NVDA"
        assert r.watchlist_changes[0].action == "add"
        assert r.trades == []

    def test_watchlist_remove(self, client):
        r = client.complete("remove TSLA from my watchlist")
        assert r.watchlist_changes[0].ticker == "TSLA"
        assert r.watchlist_changes[0].action == "remove"

    def test_unknown_request_returns_help_message(self, client):
        r = client.complete("What's the weather in Paris?")
        assert r.message
        assert r.trades == []
        assert r.watchlist_changes == []

    def test_deterministic_same_input_same_output(self, client):
        a = client.complete("buy 5 NVDA")
        b = client.complete("buy 5 NVDA")
        assert a.model_dump() == b.model_dump()


class TestEnvVarMode:
    def test_llm_mock_env_true_enables_mock(self, monkeypatch):
        monkeypatch.setenv("LLM_MOCK", "true")
        reset_llm_client()
        c = get_llm_client()
        assert c.mock is True

    def test_llm_mock_env_false_disables_mock(self, monkeypatch):
        monkeypatch.setenv("LLM_MOCK", "false")
        reset_llm_client()
        c = get_llm_client()
        assert c.mock is False

    def test_llm_mock_env_unset_disables_mock(self, monkeypatch):
        monkeypatch.delenv("LLM_MOCK", raising=False)
        reset_llm_client()
        c = get_llm_client()
        assert c.mock is False

    def test_llm_mock_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("LLM_MOCK", "TRUE")
        reset_llm_client()
        c = get_llm_client()
        assert c.mock is True

    def test_get_llm_client_is_singleton(self, monkeypatch):
        monkeypatch.setenv("LLM_MOCK", "true")
        reset_llm_client()
        a = get_llm_client()
        b = get_llm_client()
        assert a is b

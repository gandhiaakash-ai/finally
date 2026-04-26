"""Tests for the chat orchestrator end-to-end.

These tests exercise the real ``app.portfolio.execute_trade`` path so a chat
"buy 1 AAPL" hits the same validation and persistence as a manual REST trade.
The market data source is stubbed because we don't need a background poller.
"""

from __future__ import annotations

import pytest

from app.db import chat as chat_db
from app.db import positions as positions_db
from app.db import trades as trades_db
from app.db import users as users_db
from app.db import watchlist as watchlist_db
from app.db.connection import reset_connection
from app.db.schema import init_db
from app.llm.client import LLMClient
from app.llm.orchestrator import handle_chat_message
from app.llm.schema import LLMResponse, TradeAction, WatchlistChange
from app.market import PriceCache


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "test.db"))
    reset_connection()
    init_db()
    yield
    reset_connection()


@pytest.fixture
def cache():
    c = PriceCache()
    c.update("AAPL", 200.0)
    c.update("NVDA", 500.0)
    return c


class _RecordingSource:
    """Stand-in for MarketDataSource that records add/remove calls."""

    def __init__(self):
        self.added: list[str] = []
        self.removed: list[str] = []

    async def add_ticker(self, ticker):
        self.added.append(ticker)

    async def remove_ticker(self, ticker):
        self.removed.append(ticker)


class TestHappyPath:
    async def test_greeting_persists_user_and_assistant(self, db, cache):
        result = await handle_chat_message(
            "hello",
            price_cache=cache,
            llm_client=LLMClient(mock=True),
        )
        assert result.message
        assert result.trades == []
        assert result.watchlist_changes == []

        history = chat_db.list_recent_messages()
        assert [m.role for m in history] == ["user", "assistant"]
        assert history[0].content == "hello"
        assert history[1].actions == {"trades": [], "watchlist_changes": []}

    async def test_buy_trade_executes_and_persists_via_real_helper(self, db, cache):
        result = await handle_chat_message(
            "buy 3 AAPL",
            price_cache=cache,
            llm_client=LLMClient(mock=True),
        )
        assert len(result.trades) == 1
        t = result.trades[0]
        assert t.status == "filled"
        assert t.ticker == "AAPL" and t.quantity == 3
        assert t.price == 200.0
        assert t.error is None

        assert users_db.get_cash_balance() == 10000.0 - 600.0
        pos = positions_db.get_position("AAPL")
        assert pos is not None and pos.quantity == 3
        assert len(trades_db.list_trades()) == 1

    async def test_failed_trade_returns_error_without_crashing(self, db, cache):
        result = await handle_chat_message(
            "buy 999 AAPL",
            price_cache=cache,
            llm_client=LLMClient(mock=True),
        )
        assert len(result.trades) == 1
        t = result.trades[0]
        assert t.status == "failed"
        assert "insufficient cash" in t.error.lower()
        assert users_db.get_cash_balance() == 10000.0
        assert positions_db.get_position("AAPL") is None
        assert trades_db.list_trades() == []

    async def test_assistant_actions_payload_persisted_with_fill_details(self, db, cache):
        await handle_chat_message(
            "buy 1 AAPL",
            price_cache=cache,
            llm_client=LLMClient(mock=True),
        )
        msgs = chat_db.list_recent_messages()
        assistant = next(m for m in msgs if m.role == "assistant")
        assert assistant.actions["trades"][0]["status"] == "filled"
        assert assistant.actions["trades"][0]["ticker"] == "AAPL"
        assert assistant.actions["trades"][0]["price"] == 200.0


class TestWatchlistActions:
    async def test_add_inserts_db_and_calls_market_source(self, db, cache):
        source = _RecordingSource()
        result = await handle_chat_message(
            "add PYPL to my watchlist",
            price_cache=cache,
            market_source=source,
            llm_client=LLMClient(mock=True),
        )
        assert "PYPL" in watchlist_db.list_tickers()
        assert source.added == ["PYPL"]
        assert source.removed == []
        assert result.watchlist_changes[0].status == "applied"

    async def test_add_existing_ticker_skips_market_source(self, db, cache):
        source = _RecordingSource()
        result = await handle_chat_message(
            "add AAPL to my watchlist",
            price_cache=cache,
            market_source=source,
            llm_client=LLMClient(mock=True),
        )
        assert source.added == []
        assert result.watchlist_changes[0].status == "applied"

    async def test_remove_existing_ticker_calls_market_source(self, db, cache):
        source = _RecordingSource()
        result = await handle_chat_message(
            "remove TSLA from my watchlist",
            price_cache=cache,
            market_source=source,
            llm_client=LLMClient(mock=True),
        )
        assert "TSLA" not in watchlist_db.list_tickers()
        assert source.removed == ["TSLA"]
        assert result.watchlist_changes[0].status == "applied"

    async def test_remove_unknown_ticker_returns_failure(self, db, cache):
        source = _RecordingSource()
        result = await handle_chat_message(
            "remove ZZZZ from my watchlist",
            price_cache=cache,
            market_source=source,
            llm_client=LLMClient(mock=True),
        )
        assert result.watchlist_changes[0].status == "failed"
        assert "ZZZZ" in result.watchlist_changes[0].error
        assert source.removed == []

    async def test_no_market_source_skips_remote_call_silently(self, db, cache):
        result = await handle_chat_message(
            "add PYPL to my watchlist",
            price_cache=cache,
            market_source=None,
            llm_client=LLMClient(mock=True),
        )
        assert "PYPL" in watchlist_db.list_tickers()
        assert result.watchlist_changes[0].status == "applied"


class _StubLLM:
    def __init__(self, response: LLMResponse):
        self._response = response
        self.last_call: dict | None = None

    @property
    def mock(self) -> bool:
        return True

    def complete(self, user_message, *, portfolio_context="", history=None):
        self.last_call = {
            "user_message": user_message,
            "portfolio_context": portfolio_context,
            "history": list(history or []),
        }
        return self._response


class TestContextWiring:
    async def test_portfolio_context_and_history_passed_to_llm(self, db, cache):
        chat_db.insert_message(role="user", content="prior question")
        chat_db.insert_message(role="assistant", content="prior answer")

        stub = _StubLLM(LLMResponse(message="ok"))
        await handle_chat_message(
            "current question",
            price_cache=cache,
            llm_client=stub,
        )
        assert stub.last_call["user_message"] == "current question"
        assert "Cash: $10,000.00" in stub.last_call["portfolio_context"]
        contents = [h["content"] for h in stub.last_call["history"]]
        assert "current question" not in contents
        assert "prior question" in contents
        assert "prior answer" in contents

    async def test_multiple_trades_and_watchlist_in_one_turn(self, db, cache):
        positions_db.upsert_position("NVDA", quantity=2, avg_cost=400.0)

        stub = _StubLLM(
            LLMResponse(
                message="Doing it.",
                trades=[
                    TradeAction(ticker="AAPL", side="buy", quantity=1),
                    TradeAction(ticker="NVDA", side="sell", quantity=2),
                ],
                watchlist_changes=[
                    WatchlistChange(ticker="PYPL", action="add"),
                    WatchlistChange(ticker="TSLA", action="remove"),
                ],
            )
        )
        source = _RecordingSource()
        result = await handle_chat_message(
            "execute plan",
            price_cache=cache,
            market_source=source,
            llm_client=stub,
        )
        assert [(t.ticker, t.status) for t in result.trades] == [
            ("AAPL", "filled"),
            ("NVDA", "filled"),
        ]
        assert [(w.ticker, w.action, w.status) for w in result.watchlist_changes] == [
            ("PYPL", "add", "applied"),
            ("TSLA", "remove", "applied"),
        ]
        assert source.added == ["PYPL"]
        assert source.removed == ["TSLA"]


class _BoomLLM:
    @property
    def mock(self) -> bool:
        return False

    def complete(self, *_a, **_k):
        from app.llm.client import LLMError
        raise LLMError("provider down")


class TestLLMFailure:
    async def test_llm_error_returns_apologetic_message_and_persists(self, db, cache):
        result = await handle_chat_message(
            "hi",
            price_cache=cache,
            llm_client=_BoomLLM(),
        )
        assert "unavailable" in result.message.lower()
        assert result.trades == [] and result.watchlist_changes == []
        msgs = chat_db.list_recent_messages()
        assert [m.role for m in msgs] == ["user", "assistant"]
        assert "unavailable" in msgs[1].content.lower()
        assert msgs[1].actions is None

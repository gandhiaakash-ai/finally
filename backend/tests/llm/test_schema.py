"""Tests for the LLM structured-output schema."""

import pytest
from pydantic import ValidationError

from app.llm.schema import LLMResponse, TradeAction, WatchlistChange


class TestTradeAction:
    def test_minimal_trade(self):
        t = TradeAction(ticker="AAPL", side="buy", quantity=1)
        assert t.ticker == "AAPL"
        assert t.side == "buy"
        assert t.quantity == 1.0

    def test_ticker_is_uppercased_and_stripped(self):
        t = TradeAction(ticker="  aapl  ", side="sell", quantity=2)
        assert t.ticker == "AAPL"

    def test_fractional_quantity_allowed(self):
        t = TradeAction(ticker="GOOGL", side="buy", quantity=0.25)
        assert t.quantity == 0.25

    def test_invalid_side(self):
        with pytest.raises(ValidationError):
            TradeAction(ticker="AAPL", side="hold", quantity=1)

    def test_zero_quantity_rejected(self):
        with pytest.raises(ValidationError):
            TradeAction(ticker="AAPL", side="buy", quantity=0)

    def test_negative_quantity_rejected(self):
        with pytest.raises(ValidationError):
            TradeAction(ticker="AAPL", side="buy", quantity=-1)


class TestWatchlistChange:
    def test_add(self):
        w = WatchlistChange(ticker="nvda", action="add")
        assert w.ticker == "NVDA"
        assert w.action == "add"

    def test_remove(self):
        w = WatchlistChange(ticker="META", action="remove")
        assert w.action == "remove"

    def test_invalid_action(self):
        with pytest.raises(ValidationError):
            WatchlistChange(ticker="META", action="toggle")


class TestLLMResponse:
    def test_message_only(self):
        r = LLMResponse(message="hello")
        assert r.message == "hello"
        assert r.trades == []
        assert r.watchlist_changes == []

    def test_with_trades_and_watchlist(self):
        r = LLMResponse(
            message="Doing it.",
            trades=[TradeAction(ticker="AAPL", side="buy", quantity=10)],
            watchlist_changes=[WatchlistChange(ticker="PYPL", action="add")],
        )
        assert len(r.trades) == 1
        assert len(r.watchlist_changes) == 1

    def test_round_trip_through_json(self):
        raw = (
            '{"message": "ok", "trades": [{"ticker": "AAPL", "side": "buy", '
            '"quantity": 5}], "watchlist_changes": []}'
        )
        r = LLMResponse.model_validate_json(raw)
        assert r.trades[0].ticker == "AAPL"
        assert r.trades[0].quantity == 5.0

    def test_missing_message_rejected(self):
        with pytest.raises(ValidationError):
            LLMResponse.model_validate_json('{"trades": []}')

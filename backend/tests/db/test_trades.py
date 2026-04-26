"""Trades CRUD tests."""

from __future__ import annotations

import pytest

from app.db import trades


def test_insert_returns_trade(db):
    t = trades.insert_trade("AAPL", "buy", 5, 190.0)
    assert t.ticker == "AAPL"
    assert t.side == "buy"
    assert t.quantity == 5
    assert t.price == 190.0
    assert t.id
    assert t.executed_at


def test_invalid_side_rejected(db):
    with pytest.raises(ValueError):
        trades.insert_trade("AAPL", "short", 1, 190.0)  # type: ignore[arg-type]


def test_list_returns_newest_first(db):
    trades.insert_trade("AAPL", "buy", 1, 100.0)
    trades.insert_trade("AAPL", "sell", 1, 110.0)
    trades.insert_trade("MSFT", "buy", 1, 400.0)
    listed = trades.list_trades()
    assert [(t.ticker, t.side) for t in listed] == [
        ("MSFT", "buy"),
        ("AAPL", "sell"),
        ("AAPL", "buy"),
    ]


def test_list_respects_limit(db):
    for _ in range(5):
        trades.insert_trade("AAPL", "buy", 1, 100.0)
    assert len(trades.list_trades(limit=2)) == 2


def test_explicit_executed_at_preserved(db):
    ts = "2025-01-01T12:00:00+00:00"
    t = trades.insert_trade("AAPL", "buy", 1, 100.0, executed_at=ts)
    assert t.executed_at == ts


def test_ticker_normalised(db):
    t = trades.insert_trade(" aapl ", "buy", 1, 100.0)
    assert t.ticker == "AAPL"

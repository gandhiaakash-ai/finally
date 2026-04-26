"""Watchlist CRUD tests."""

from __future__ import annotations

from app.db import DEFAULT_TICKERS, watchlist


def test_default_seeded_listed(db):
    tickers = watchlist.list_tickers()
    assert set(tickers) == set(DEFAULT_TICKERS)
    assert len(tickers) == len(DEFAULT_TICKERS)


def test_add_new_ticker_returns_true(db):
    assert watchlist.add_ticker("PYPL") is True
    assert "PYPL" in watchlist.list_tickers()


def test_add_existing_ticker_is_idempotent(db):
    assert watchlist.add_ticker("PYPL") is True
    assert watchlist.add_ticker("pypl") is False
    occurrences = [t for t in watchlist.list_tickers() if t == "PYPL"]
    assert len(occurrences) == 1


def test_remove_ticker(db):
    assert watchlist.remove_ticker("AAPL") is True
    assert "AAPL" not in watchlist.list_tickers()


def test_remove_unknown_ticker_returns_false(db):
    assert watchlist.remove_ticker("NOPE") is False


def test_tickers_normalised_to_upper(db):
    watchlist.add_ticker("  pypl ")
    assert "PYPL" in watchlist.list_tickers()


def test_other_users_isolated(db):
    watchlist.add_ticker("PYPL", user_id="other")
    default_tickers = watchlist.list_tickers()
    other_tickers = watchlist.list_tickers(user_id="other")
    assert "PYPL" not in default_tickers
    assert other_tickers == ["PYPL"]

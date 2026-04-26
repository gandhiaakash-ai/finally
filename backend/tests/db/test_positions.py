"""Positions CRUD tests."""

from __future__ import annotations

from app.db import positions


def test_no_positions_initially(db):
    assert positions.list_positions() == []
    assert positions.get_position("AAPL") is None


def test_upsert_inserts_then_updates(db):
    positions.upsert_position("AAPL", 5, 190.0)
    pos = positions.get_position("AAPL")
    assert pos is not None
    assert pos.quantity == 5
    assert pos.avg_cost == 190.0

    positions.upsert_position("AAPL", 7, 188.5)
    pos = positions.get_position("AAPL")
    assert pos.quantity == 7
    assert pos.avg_cost == 188.5

    assert len(positions.list_positions()) == 1


def test_list_positions_sorted_by_ticker(db):
    positions.upsert_position("MSFT", 1, 400.0)
    positions.upsert_position("AAPL", 1, 190.0)
    positions.upsert_position("GOOGL", 1, 175.0)
    tickers = [p.ticker for p in positions.list_positions()]
    assert tickers == ["AAPL", "GOOGL", "MSFT"]


def test_delete_existing_returns_true(db):
    positions.upsert_position("AAPL", 1, 190.0)
    assert positions.delete_position("AAPL") is True
    assert positions.get_position("AAPL") is None


def test_delete_missing_returns_false(db):
    assert positions.delete_position("AAPL") is False


def test_ticker_normalised(db):
    positions.upsert_position(" aapl ", 1, 190.0)
    assert positions.get_position("AAPL") is not None
    assert positions.get_position("aapl") is not None


def test_fractional_quantity_supported(db):
    positions.upsert_position("AAPL", 0.25, 190.0)
    assert positions.get_position("AAPL").quantity == 0.25

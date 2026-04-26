"""Unit tests for portfolio_summary — valuation math against the price cache."""

from __future__ import annotations

import pytest

from app.market import PriceCache
from app.portfolio import portfolio_summary
from app.portfolio.trades import execute_trade


def test_empty_portfolio_is_cash_only(db):
    cache = PriceCache()
    summary = portfolio_summary(cache)
    assert summary.cash_balance == 10_000.0
    assert summary.positions == []
    assert summary.positions_value == 0.0
    assert summary.total_value == 10_000.0
    assert summary.total_unrealized_pl == 0.0


def test_position_with_price_computes_market_value_and_pl(db):
    cache = PriceCache()
    cache.update("AAPL", 200.0)
    execute_trade("AAPL", "buy", 10.0, cache)

    cache.update("AAPL", 220.0)
    summary = portfolio_summary(cache)

    aapl = next(p for p in summary.positions if p.ticker == "AAPL")
    assert aapl.current_price == 220.0
    assert aapl.market_value == pytest.approx(2200.0)
    assert aapl.unrealized_pl == pytest.approx(200.0)
    assert aapl.unrealized_pl_percent == pytest.approx(10.0)
    assert summary.total_value == pytest.approx(8_000.0 + 2_200.0)


def test_position_without_cached_price_falls_back_to_cost_basis(db):
    cache = PriceCache()
    cache.update("AAPL", 200.0)
    execute_trade("AAPL", "buy", 10.0, cache)

    cache.remove("AAPL")
    summary = portfolio_summary(cache)
    aapl = next(p for p in summary.positions if p.ticker == "AAPL")
    assert aapl.current_price is None
    assert aapl.market_value == pytest.approx(2_000.0)
    assert aapl.unrealized_pl == 0.0

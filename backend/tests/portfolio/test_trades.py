"""Unit tests for execute_trade — validation + weighted-avg accounting."""

from __future__ import annotations

import pytest

from app.db import positions as positions_db
from app.db import trades as trades_db
from app.db import users
from app.market import PriceCache
from app.portfolio import TradeError, execute_trade


@pytest.fixture
def cache() -> PriceCache:
    c = PriceCache()
    c.update("AAPL", 200.0)
    c.update("MSFT", 400.0)
    return c


def test_buy_records_trade_position_and_cash(db, cache):
    result = execute_trade("AAPL", "buy", 10.0, cache)

    assert result.trade.ticker == "AAPL"
    assert result.trade.side == "buy"
    assert result.trade.quantity == 10.0
    assert result.trade.price == 200.0

    pos = positions_db.get_position("AAPL")
    assert pos is not None
    assert pos.quantity == 10.0
    assert pos.avg_cost == 200.0

    assert users.get_cash_balance() == 10_000.0 - 2_000.0


def test_buy_uses_weighted_average_cost_on_subsequent_buys(db, cache):
    execute_trade("AAPL", "buy", 10.0, cache)
    cache.update("AAPL", 220.0)
    execute_trade("AAPL", "buy", 10.0, cache)

    pos = positions_db.get_position("AAPL")
    assert pos is not None
    assert pos.quantity == 20.0
    assert pos.avg_cost == pytest.approx(210.0)


def test_sell_reduces_quantity_and_keeps_avg_cost(db, cache):
    execute_trade("AAPL", "buy", 10.0, cache)
    cache.update("AAPL", 250.0)
    execute_trade("AAPL", "sell", 4.0, cache)

    pos = positions_db.get_position("AAPL")
    assert pos is not None
    assert pos.quantity == 6.0
    assert pos.avg_cost == 200.0
    assert users.get_cash_balance() == pytest.approx(10_000.0 - 2_000.0 + 4 * 250.0)


def test_sell_full_quantity_deletes_position(db, cache):
    execute_trade("AAPL", "buy", 5.0, cache)
    execute_trade("AAPL", "sell", 5.0, cache)
    assert positions_db.get_position("AAPL") is None


def test_buy_insufficient_cash_raises(db, cache):
    with pytest.raises(TradeError, match="Insufficient cash"):
        execute_trade("AAPL", "buy", 100.0, cache)


def test_sell_insufficient_shares_raises(db, cache):
    execute_trade("AAPL", "buy", 1.0, cache)
    with pytest.raises(TradeError, match="Insufficient shares"):
        execute_trade("AAPL", "sell", 10.0, cache)


def test_sell_with_no_position_raises(db, cache):
    with pytest.raises(TradeError, match="Insufficient shares"):
        execute_trade("AAPL", "sell", 1.0, cache)


def test_unknown_ticker_raises(db, cache):
    with pytest.raises(TradeError, match="No price"):
        execute_trade("ZZZZ", "buy", 1.0, cache)


def test_zero_quantity_raises(db, cache):
    with pytest.raises(TradeError, match="greater than zero"):
        execute_trade("AAPL", "buy", 0.0, cache)


def test_negative_quantity_raises(db, cache):
    with pytest.raises(TradeError, match="greater than zero"):
        execute_trade("AAPL", "buy", -5.0, cache)


def test_invalid_side_raises(db, cache):
    with pytest.raises(TradeError, match="Invalid side"):
        execute_trade("AAPL", "hold", 1.0, cache)  # type: ignore[arg-type]


def test_empty_ticker_raises(db, cache):
    with pytest.raises(TradeError, match="required"):
        execute_trade("", "buy", 1.0, cache)


def test_trade_appended_to_history(db, cache):
    execute_trade("AAPL", "buy", 1.0, cache)
    execute_trade("MSFT", "buy", 1.0, cache)
    history = trades_db.list_trades()
    assert [t.ticker for t in history] == ["MSFT", "AAPL"]

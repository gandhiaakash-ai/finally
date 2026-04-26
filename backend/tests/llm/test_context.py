"""Tests for the portfolio-context builder and history loader."""

import pytest

from app.db import chat as chat_db
from app.db import positions as positions_db
from app.db import users as users_db
from app.db.connection import reset_connection
from app.db.schema import init_db
from app.llm.context import build_snapshot, load_history, render_snapshot
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


class TestBuildSnapshot:
    def test_default_seed_no_positions(self, db, cache):
        snap = build_snapshot(cache)
        assert snap.cash == 10000.0
        assert snap.total_value == 10000.0
        assert snap.positions == []
        tickers = [w.ticker for w in snap.watchlist]
        assert "AAPL" in tickers and "NVDA" in tickers

    def test_position_with_live_price_computes_pl(self, db, cache):
        positions_db.upsert_position("AAPL", quantity=10, avg_cost=180.0)
        snap = build_snapshot(cache)
        line = next(p for p in snap.positions if p.ticker == "AAPL")
        assert line.price == 200.0
        assert line.market_value == pytest.approx(2000.0)
        assert line.unrealized_pl == pytest.approx(200.0)
        assert line.unrealized_pl_pct == pytest.approx((200.0 / 1800.0) * 100)
        assert snap.total_value == pytest.approx(10000.0 + 2000.0)

    def test_position_without_price_falls_back_to_zero_value(self, db, cache):
        positions_db.upsert_position("ZZZ", quantity=5, avg_cost=10.0)
        snap = build_snapshot(cache)
        line = next(p for p in snap.positions if p.ticker == "ZZZ")
        assert line.price is None
        assert line.market_value == 0.0
        assert line.unrealized_pl == 0.0
        assert line.unrealized_pl_pct is None

    def test_watchlist_lines_pull_prices(self, db, cache):
        snap = build_snapshot(cache)
        prices = {w.ticker: w.price for w in snap.watchlist}
        assert prices["AAPL"] == 200.0
        assert prices["NVDA"] == 500.0
        assert prices["MSFT"] is None  # no cache entry yet

    def test_cash_balance_reflects_updates(self, db, cache):
        users_db.update_cash_balance(7500.0)
        snap = build_snapshot(cache)
        assert snap.cash == 7500.0


class TestRenderSnapshot:
    def test_renders_cash_and_total(self, db, cache):
        snap = build_snapshot(cache)
        text = render_snapshot(snap)
        assert "Cash: $10,000.00" in text
        assert "Total portfolio value: $10,000.00" in text

    def test_renders_no_positions_message(self, db, cache):
        text = render_snapshot(build_snapshot(cache))
        assert "Positions: none" in text

    def test_renders_position_with_pl(self, db, cache):
        positions_db.upsert_position("AAPL", quantity=10, avg_cost=180.0)
        text = render_snapshot(build_snapshot(cache))
        assert "AAPL" in text
        assert "qty=10" in text
        assert "P&L=$+200.00" in text

    def test_renders_watchlist(self, db, cache):
        text = render_snapshot(build_snapshot(cache))
        assert "Watchlist:" in text
        assert "AAPL: $200.00" in text


class TestLoadHistory:
    def test_empty_when_no_messages(self, db):
        assert load_history() == []

    def test_returns_oldest_first_within_limit(self, db):
        for i in range(5):
            chat_db.insert_message(role="user", content=f"u{i}")
            chat_db.insert_message(role="assistant", content=f"a{i}")
        history = load_history(limit=4)
        assert len(history) == 4
        assert [h["content"] for h in history] == ["u3", "a3", "u4", "a4"]
        assert all(h["role"] in ("user", "assistant") for h in history)

    def test_role_and_content_keys_only(self, db):
        chat_db.insert_message(role="user", content="hi")
        h = load_history()
        assert set(h[0].keys()) == {"role", "content"}

"""Schema creation and seed-data tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.db import (
    DEFAULT_CASH_BALANCE,
    DEFAULT_TICKERS,
    DEFAULT_USER_ID,
    init_db,
)
from app.db import connection as conn_mod

EXPECTED_TABLES = {
    "users_profile",
    "watchlist",
    "positions",
    "trades",
    "portfolio_snapshots",
    "chat_messages",
}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {r["name"] for r in rows}


def test_init_creates_all_tables(db):
    assert EXPECTED_TABLES.issubset(_table_names(db))


def test_default_user_seeded(db):
    row = db.execute(
        "SELECT id, cash_balance FROM users_profile WHERE id = ?",
        (DEFAULT_USER_ID,),
    ).fetchone()
    assert row is not None
    assert row["id"] == DEFAULT_USER_ID
    assert row["cash_balance"] == DEFAULT_CASH_BALANCE


def test_default_watchlist_seeded(db):
    rows = db.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ?", (DEFAULT_USER_ID,)
    ).fetchall()
    tickers = {r["ticker"] for r in rows}
    assert tickers == set(DEFAULT_TICKERS)


def test_init_is_idempotent(db):
    """Running init twice does not double-seed or fail."""
    init_db()
    user_count = db.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0]
    watch_count = db.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
    assert user_count == 1
    assert watch_count == len(DEFAULT_TICKERS)


def test_lazy_init_creates_db_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """If the db file is missing, init_db creates it under the configured path."""
    target = tmp_path / "lazy.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(target))
    conn_mod.reset_connection()
    try:
        assert not target.exists()
        init_db()
        assert target.exists()
    finally:
        conn_mod.reset_connection()


def test_watchlist_unique_constraint(db):
    db.execute(
        "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        ("x1", DEFAULT_USER_ID, "ZZZZ", "2026-01-01T00:00:00+00:00"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            ("x2", DEFAULT_USER_ID, "ZZZZ", "2026-01-01T00:00:01+00:00"),
        )


def test_trades_side_check_constraint(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)
            VALUES ('t1', ?, 'AAPL', 'short', 1, 100.0, '2026-01-01T00:00:00+00:00')
            """,
            (DEFAULT_USER_ID,),
        )


def test_chat_role_check_constraint(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)
            VALUES ('c1', ?, 'system', 'oops', NULL, '2026-01-01T00:00:00+00:00')
            """,
            (DEFAULT_USER_ID,),
        )

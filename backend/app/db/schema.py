"""Schema DDL and lazy initialisation for FinAlly's SQLite database.

`init_db()` is idempotent: it creates any missing tables and seeds default
data only when the user / watchlist tables are empty. Safe to call multiple
times (e.g. on FastAPI startup and again from tests).
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from app.db.connection import DEFAULT_USER_ID, get_connection

DEFAULT_CASH_BALANCE = 10_000.0
DEFAULT_TICKERS: tuple[str, ...] = (
    "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
    "NVDA", "META", "JPM", "V", "NFLX",
)

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS users_profile (
    id            TEXT PRIMARY KEY,
    cash_balance  REAL NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    id        TEXT PRIMARY KEY,
    user_id   TEXT NOT NULL DEFAULT 'default',
    ticker    TEXT NOT NULL,
    added_at  TEXT NOT NULL,
    UNIQUE (user_id, ticker)
);
CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist (user_id);

CREATE TABLE IF NOT EXISTS positions (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT 'default',
    ticker      TEXT NOT NULL,
    quantity    REAL NOT NULL,
    avg_cost    REAL NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE (user_id, ticker)
);
CREATE INDEX IF NOT EXISTS idx_positions_user ON positions (user_id);

CREATE TABLE IF NOT EXISTS trades (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL DEFAULT 'default',
    ticker       TEXT NOT NULL,
    side         TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity     REAL NOT NULL,
    price        REAL NOT NULL,
    executed_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trades_user_time ON trades (user_id, executed_at);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL DEFAULT 'default',
    total_value  REAL NOT NULL,
    recorded_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_user_time
    ON portfolio_snapshots (user_id, recorded_at);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT 'default',
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    actions     TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_user_time ON chat_messages (user_id, created_at);
"""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db(conn: sqlite3.Connection | None = None) -> None:
    """Create schema and seed defaults if needed. Idempotent."""
    conn = conn or get_connection()
    conn.executescript(SCHEMA_DDL)
    _seed_defaults(conn)


def _seed_defaults(conn: sqlite3.Connection) -> None:
    now = _utcnow_iso()
    cur = conn.execute(
        "SELECT 1 FROM users_profile WHERE id = ?", (DEFAULT_USER_ID,)
    )
    if cur.fetchone() is None:
        conn.execute(
            "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
            (DEFAULT_USER_ID, DEFAULT_CASH_BALANCE, now),
        )

    cur = conn.execute(
        "SELECT COUNT(*) FROM watchlist WHERE user_id = ?", (DEFAULT_USER_ID,)
    )
    if cur.fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            [
                (str(uuid.uuid4()), DEFAULT_USER_ID, ticker, now)
                for ticker in DEFAULT_TICKERS
            ],
        )

"""Watchlist CRUD.

Tickers are stored upper-cased and de-duplicated per user. `add_ticker` is
idempotent — re-adding an existing ticker is a no-op and returns False.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from app.db.connection import DEFAULT_USER_ID, get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def list_tickers(
    user_id: str = DEFAULT_USER_ID,
    conn: sqlite3.Connection | None = None,
) -> list[str]:
    """Return tickers in insertion order."""
    conn = conn or get_connection()
    rows = conn.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY added_at, ticker",
        (user_id,),
    ).fetchall()
    return [r["ticker"] for r in rows]


def add_ticker(
    ticker: str,
    user_id: str = DEFAULT_USER_ID,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Add a ticker. Returns True if inserted, False if already present."""
    conn = conn or get_connection()
    ticker = ticker.strip().upper()
    try:
        conn.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, ticker, _now()),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def remove_ticker(
    ticker: str,
    user_id: str = DEFAULT_USER_ID,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Remove a ticker. Returns True if a row was deleted."""
    conn = conn or get_connection()
    ticker = ticker.strip().upper()
    cur = conn.execute(
        "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    )
    return cur.rowcount > 0

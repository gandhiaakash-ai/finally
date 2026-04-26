"""User profile (single-user) CRUD.

Currently one row per user_id; the default row is created by `init_db`.
"""

from __future__ import annotations

import sqlite3

from app.db.connection import DEFAULT_USER_ID, get_connection


def get_cash_balance(
    user_id: str = DEFAULT_USER_ID,
    conn: sqlite3.Connection | None = None,
) -> float:
    """Return the user's current cash balance. Raises if the user is missing."""
    conn = conn or get_connection()
    row = conn.execute(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)
    ).fetchone()
    if row is None:
        raise LookupError(f"User profile not found: {user_id}")
    return float(row["cash_balance"])


def update_cash_balance(
    cash_balance: float,
    user_id: str = DEFAULT_USER_ID,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Overwrite the user's cash balance."""
    conn = conn or get_connection()
    cur = conn.execute(
        "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
        (cash_balance, user_id),
    )
    if cur.rowcount == 0:
        raise LookupError(f"User profile not found: {user_id}")

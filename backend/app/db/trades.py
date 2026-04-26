"""Trade history CRUD (append-only log)."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from app.db.connection import DEFAULT_USER_ID, get_connection

Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class Trade:
    id: str
    ticker: str
    side: Side
    quantity: float
    price: float
    executed_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def insert_trade(
    ticker: str,
    side: Side,
    quantity: float,
    price: float,
    user_id: str = DEFAULT_USER_ID,
    executed_at: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> Trade:
    """Append a trade. Returns the inserted Trade."""
    conn = conn or get_connection()
    if side not in ("buy", "sell"):
        raise ValueError(f"Invalid side: {side!r}")
    ticker = ticker.strip().upper()
    trade_id = str(uuid.uuid4())
    ts = executed_at or _now()
    conn.execute(
        """
        INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (trade_id, user_id, ticker, side, quantity, price, ts),
    )
    return Trade(
        id=trade_id, ticker=ticker, side=side,
        quantity=quantity, price=price, executed_at=ts,
    )


def list_trades(
    user_id: str = DEFAULT_USER_ID,
    limit: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[Trade]:
    """Return trades newest-first. `limit` caps the result count when set."""
    conn = conn or get_connection()
    sql = (
        "SELECT id, ticker, side, quantity, price, executed_at FROM trades "
        "WHERE user_id = ? ORDER BY executed_at DESC, rowid DESC"
    )
    params: tuple = (user_id,)
    if limit is not None:
        sql += " LIMIT ?"
        params = (user_id, int(limit))
    rows = conn.execute(sql, params).fetchall()
    return [
        Trade(
            id=r["id"],
            ticker=r["ticker"],
            side=r["side"],
            quantity=float(r["quantity"]),
            price=float(r["price"]),
            executed_at=r["executed_at"],
        )
        for r in rows
    ]

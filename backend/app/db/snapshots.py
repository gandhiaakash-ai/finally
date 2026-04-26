"""Portfolio value snapshots (P&L chart source)."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.db.connection import DEFAULT_USER_ID, get_connection


@dataclass(frozen=True)
class Snapshot:
    id: str
    total_value: float
    recorded_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def insert_snapshot(
    total_value: float,
    user_id: str = DEFAULT_USER_ID,
    recorded_at: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> Snapshot:
    """Append a portfolio total-value snapshot."""
    conn = conn or get_connection()
    snap_id = str(uuid.uuid4())
    ts = recorded_at or _now()
    conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
        "VALUES (?, ?, ?, ?)",
        (snap_id, user_id, total_value, ts),
    )
    return Snapshot(id=snap_id, total_value=total_value, recorded_at=ts)


def list_snapshots(
    user_id: str = DEFAULT_USER_ID,
    since: str | None = None,
    limit: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[Snapshot]:
    """Return snapshots oldest-first. `since` filters to recorded_at >= ISO ts."""
    conn = conn or get_connection()
    sql = (
        "SELECT id, total_value, recorded_at FROM portfolio_snapshots "
        "WHERE user_id = ?"
    )
    params: list = [user_id]
    if since is not None:
        sql += " AND recorded_at >= ?"
        params.append(since)
    sql += " ORDER BY recorded_at ASC, rowid ASC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [
        Snapshot(
            id=r["id"],
            total_value=float(r["total_value"]),
            recorded_at=r["recorded_at"],
        )
        for r in rows
    ]

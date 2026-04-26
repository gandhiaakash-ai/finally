"""SQLite connection management.

The database file lives at the path returned by `db_path()`. This defaults to
`<repo>/db/finally.db` but can be overridden via the `FINALLY_DB_PATH`
environment variable (used by tests and alternative deployments).

Connections are created with `check_same_thread=False` so a single connection
can be shared across the FastAPI worker threads. Writes are serialised by
SQLite's own locking; for the single-user workload this is plenty.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

DEFAULT_USER_ID = "default"

_DEFAULT_DB_DIR = Path(__file__).resolve().parents[3] / "db"
_DEFAULT_DB_FILE = _DEFAULT_DB_DIR / "finally.db"

_lock = threading.Lock()
_connection: sqlite3.Connection | None = None
_connected_path: Path | None = None


def db_path() -> Path:
    """Return the SQLite file path, honouring `FINALLY_DB_PATH` if set."""
    env = os.environ.get("FINALLY_DB_PATH")
    return Path(env) if env else _DEFAULT_DB_FILE


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(path),
        check_same_thread=False,
        isolation_level=None,  # autocommit; explicit BEGIN inside transactions
        detect_types=sqlite3.PARSE_DECLTYPES,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_connection() -> sqlite3.Connection:
    """Return a process-wide singleton connection, creating it on first call."""
    global _connection, _connected_path
    target = db_path()
    with _lock:
        if _connection is None or _connected_path != target:
            if _connection is not None:
                _connection.close()
            _connection = _connect(target)
            _connected_path = target
        return _connection


def reset_connection() -> None:
    """Close and forget the cached connection. Intended for tests."""
    global _connection, _connected_path
    with _lock:
        if _connection is not None:
            _connection.close()
        _connection = None
        _connected_path = None

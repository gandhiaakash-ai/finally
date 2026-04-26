"""Shared fixtures for DB tests.

`db` provides a freshly-initialised SQLite database isolated to the test via
`FINALLY_DB_PATH`. The cached process-wide connection is reset around each
test so paths don't leak between tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.db import connection as conn_mod
from app.db import init_db


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Yield a freshly-seeded sqlite3.Connection backed by a temp file."""
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "test.db"))
    conn_mod.reset_connection()
    init_db()
    yield conn_mod.get_connection()
    conn_mod.reset_connection()

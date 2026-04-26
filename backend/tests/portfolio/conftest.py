"""Shared fixtures for portfolio-package tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.db import connection as conn_mod
from app.db import init_db


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Freshly-initialised SQLite database isolated to one test."""
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "test.db"))
    conn_mod.reset_connection()
    init_db()
    yield conn_mod.get_connection()
    conn_mod.reset_connection()

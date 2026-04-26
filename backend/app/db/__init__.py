"""SQLite persistence layer for FinAlly.

Use the connection helpers and `init_db` from this module; access CRUD
functions via the per-table submodules:

    from app.db import init_db, get_connection, DEFAULT_USER_ID
    from app.db import users, watchlist, positions, trades, snapshots, chat
"""

from app.db import chat, positions, snapshots, trades, users, watchlist
from app.db.connection import DEFAULT_USER_ID, db_path, get_connection, reset_connection
from app.db.schema import DEFAULT_CASH_BALANCE, DEFAULT_TICKERS, init_db

__all__ = [
    "DEFAULT_CASH_BALANCE",
    "DEFAULT_TICKERS",
    "DEFAULT_USER_ID",
    "chat",
    "db_path",
    "get_connection",
    "init_db",
    "positions",
    "reset_connection",
    "snapshots",
    "trades",
    "users",
    "watchlist",
]

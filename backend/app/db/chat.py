"""Chat message history.

`actions` is stored as a JSON-encoded blob. Callers pass either ``None`` (user
messages) or a JSON-serialisable object (executed trades / watchlist changes
for assistant turns) and get the parsed value back from `list_recent_messages`.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from app.db.connection import DEFAULT_USER_ID, get_connection

Role = Literal["user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    id: str
    role: Role
    content: str
    actions: Any | None
    created_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def insert_message(
    role: Role,
    content: str,
    actions: Any | None = None,
    user_id: str = DEFAULT_USER_ID,
    created_at: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> ChatMessage:
    """Append a chat message."""
    conn = conn or get_connection()
    if role not in ("user", "assistant"):
        raise ValueError(f"Invalid role: {role!r}")
    msg_id = str(uuid.uuid4())
    ts = created_at or _now()
    actions_json = None if actions is None else json.dumps(actions)
    conn.execute(
        """
        INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (msg_id, user_id, role, content, actions_json, ts),
    )
    return ChatMessage(
        id=msg_id, role=role, content=content, actions=actions, created_at=ts,
    )


def list_recent_messages(
    limit: int = 50,
    user_id: str = DEFAULT_USER_ID,
    conn: sqlite3.Connection | None = None,
) -> list[ChatMessage]:
    """Return up to `limit` most recent messages, ordered oldest-first."""
    conn = conn or get_connection()
    rows = conn.execute(
        """
        SELECT id, role, content, actions, created_at
          FROM chat_messages
         WHERE user_id = ?
         ORDER BY created_at DESC, rowid DESC
         LIMIT ?
        """,
        (user_id, int(limit)),
    ).fetchall()
    msgs = [
        ChatMessage(
            id=r["id"],
            role=r["role"],
            content=r["content"],
            actions=json.loads(r["actions"]) if r["actions"] else None,
            created_at=r["created_at"],
        )
        for r in rows
    ]
    msgs.reverse()
    return msgs

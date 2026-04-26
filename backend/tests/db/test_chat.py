"""Chat-message CRUD tests."""

from __future__ import annotations

import pytest

from app.db import chat


def test_insert_user_message(db):
    m = chat.insert_message("user", "hello")
    assert m.role == "user"
    assert m.content == "hello"
    assert m.actions is None


def test_insert_assistant_with_actions(db):
    actions = {"trades": [{"ticker": "AAPL", "side": "buy", "quantity": 1}]}
    m = chat.insert_message("assistant", "buying", actions=actions)
    assert m.actions == actions


def test_invalid_role_rejected(db):
    with pytest.raises(ValueError):
        chat.insert_message("system", "oops")  # type: ignore[arg-type]


def test_list_oldest_first_within_limit(db):
    chat.insert_message("user", "first")
    chat.insert_message("assistant", "second")
    chat.insert_message("user", "third")
    msgs = chat.list_recent_messages()
    assert [m.content for m in msgs] == ["first", "second", "third"]


def test_limit_returns_most_recent_window(db):
    for i in range(5):
        chat.insert_message("user", f"msg-{i}")
    msgs = chat.list_recent_messages(limit=2)
    assert [m.content for m in msgs] == ["msg-3", "msg-4"]


def test_actions_round_trip_complex_value(db):
    actions = {
        "trades": [{"ticker": "AAPL", "side": "sell", "quantity": 0.5}],
        "watchlist_changes": [{"ticker": "PYPL", "action": "add"}],
        "errors": ["insufficient cash"],
    }
    chat.insert_message("assistant", "ok", actions=actions)
    [m] = chat.list_recent_messages()
    assert m.actions == actions


def test_other_users_isolated(db):
    chat.insert_message("user", "default-only")
    chat.insert_message("user", "other-only", user_id="other")
    default_msgs = chat.list_recent_messages()
    other_msgs = chat.list_recent_messages(user_id="other")
    assert [m.content for m in default_msgs] == ["default-only"]
    assert [m.content for m in other_msgs] == ["other-only"]

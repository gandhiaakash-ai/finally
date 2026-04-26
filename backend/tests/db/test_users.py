"""Users-profile CRUD tests."""

from __future__ import annotations

import pytest

from app.db import DEFAULT_CASH_BALANCE, users


def test_get_default_balance(db):
    assert users.get_cash_balance() == DEFAULT_CASH_BALANCE


def test_update_balance_round_trip(db):
    users.update_cash_balance(7531.42)
    assert users.get_cash_balance() == 7531.42


def test_update_unknown_user_raises(db):
    with pytest.raises(LookupError):
        users.update_cash_balance(0.0, user_id="nope")


def test_get_unknown_user_raises(db):
    with pytest.raises(LookupError):
        users.get_cash_balance(user_id="ghost")

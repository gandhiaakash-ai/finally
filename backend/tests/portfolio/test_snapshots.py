"""Portfolio snapshot recorder + background loop tests."""

from __future__ import annotations

import asyncio

import pytest

from app.db import positions as positions_db
from app.db import snapshots as snapshots_db
from app.db import users
from app.market import PriceCache
from app.portfolio.snapshots import record_snapshot_now, start_snapshot_loop


def test_records_cash_only_when_no_positions(db):
    cache = PriceCache()
    snap = record_snapshot_now(cache)
    assert snap is not None
    assert snap.total_value == users.get_cash_balance()
    assert len(snapshots_db.list_snapshots()) == 1


def test_skips_when_held_ticker_has_no_price(db):
    cache = PriceCache()
    positions_db.upsert_position("AAPL", 5, 190.0)
    snap = record_snapshot_now(cache)
    assert snap is None
    assert snapshots_db.list_snapshots() == []


def test_records_total_with_priced_positions(db):
    cache = PriceCache()
    positions_db.upsert_position("AAPL", 5, 190.0)
    cache.update("AAPL", 200.0)
    snap = record_snapshot_now(cache)
    assert snap is not None
    expected = users.get_cash_balance() + 5 * 200.0
    assert snap.total_value == expected


def test_skips_when_any_held_ticker_unpriced(db):
    """Cold-start guard: even one missing price aborts the snapshot."""
    cache = PriceCache()
    positions_db.upsert_position("AAPL", 5, 190.0)
    positions_db.upsert_position("MSFT", 2, 400.0)
    cache.update("AAPL", 200.0)  # MSFT still missing
    assert record_snapshot_now(cache) is None
    assert snapshots_db.list_snapshots() == []


@pytest.mark.asyncio
async def test_loop_records_at_interval(db):
    cache = PriceCache()
    task = await start_snapshot_loop(cache, interval=0.05)
    try:
        await asyncio.sleep(0.18)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    snaps = snapshots_db.list_snapshots()
    assert len(snaps) >= 2  # ~3 ticks expected; allow scheduler slack


@pytest.mark.asyncio
async def test_loop_continues_after_iteration_error(db, monkeypatch):
    """A failure inside one iteration must not kill the loop."""
    cache = PriceCache()
    calls = {"n": 0}

    real = record_snapshot_now

    def flaky(price_cache=None, user_id="default"):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real(price_cache, user_id=user_id)

    monkeypatch.setattr("app.portfolio.snapshots.record_snapshot_now", flaky)

    task = await start_snapshot_loop(cache, interval=0.05)
    try:
        await asyncio.sleep(0.2)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert calls["n"] >= 2
    assert len(snapshots_db.list_snapshots()) >= 1


@pytest.mark.asyncio
async def test_loop_cancels_cleanly(db):
    cache = PriceCache()
    task = await start_snapshot_loop(cache, interval=10.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

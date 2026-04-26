"""Portfolio snapshots CRUD tests."""

from __future__ import annotations

from app.db import snapshots


def test_insert_returns_snapshot(db):
    s = snapshots.insert_snapshot(10000.0)
    assert s.total_value == 10000.0
    assert s.id
    assert s.recorded_at


def test_list_oldest_first(db):
    snapshots.insert_snapshot(100.0, recorded_at="2026-01-01T00:00:00+00:00")
    snapshots.insert_snapshot(200.0, recorded_at="2026-01-02T00:00:00+00:00")
    snapshots.insert_snapshot(150.0, recorded_at="2026-01-03T00:00:00+00:00")
    values = [s.total_value for s in snapshots.list_snapshots()]
    assert values == [100.0, 200.0, 150.0]


def test_since_filter(db):
    snapshots.insert_snapshot(100.0, recorded_at="2026-01-01T00:00:00+00:00")
    snapshots.insert_snapshot(200.0, recorded_at="2026-01-02T00:00:00+00:00")
    snapshots.insert_snapshot(150.0, recorded_at="2026-01-03T00:00:00+00:00")
    recent = snapshots.list_snapshots(since="2026-01-02T00:00:00+00:00")
    assert [s.total_value for s in recent] == [200.0, 150.0]


def test_limit_caps_results(db):
    for i in range(5):
        snapshots.insert_snapshot(float(i))
    assert len(snapshots.list_snapshots(limit=3)) == 3


def test_same_second_preserves_insertion_order(db):
    ts = "2026-01-01T00:00:00+00:00"
    snapshots.insert_snapshot(1.0, recorded_at=ts)
    snapshots.insert_snapshot(2.0, recorded_at=ts)
    snapshots.insert_snapshot(3.0, recorded_at=ts)
    values = [s.total_value for s in snapshots.list_snapshots()]
    assert values == [1.0, 2.0, 3.0]

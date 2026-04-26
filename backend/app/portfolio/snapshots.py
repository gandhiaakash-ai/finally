"""Portfolio snapshot recorder.

Two entry points:

- `record_snapshot_now(price_cache, user_id)` — synchronous; computes total
  portfolio value (cash + sum(qty * price)) and inserts one row into
  `portfolio_snapshots`. Skips insertion (returns ``None``) when any currently
  held ticker is missing a price in the cache, to avoid garbage data on cold
  start. Called immediately after each successful trade.

- `start_snapshot_loop(price_cache, interval)` — async; launches and returns a
  background asyncio.Task that calls `record_snapshot_now` every `interval`
  seconds. Started by the FastAPI lifespan.
"""

from __future__ import annotations

import asyncio
import logging

from app.db import positions as positions_db
from app.db import snapshots as snapshots_db
from app.db import users
from app.db.connection import DEFAULT_USER_ID
from app.db.snapshots import Snapshot
from app.market import PriceCache
from app.state import state

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 30.0


def record_snapshot_now(
    price_cache: PriceCache | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> Snapshot | None:
    """Compute and persist a single portfolio total-value snapshot.

    Returns the inserted Snapshot, or None if held positions cannot all be
    priced (cold-start guard). When the user holds nothing, the snapshot is
    cash-only and always recorded.
    """
    cache = price_cache if price_cache is not None else state.price_cache
    cash = users.get_cash_balance(user_id=user_id)
    held = positions_db.list_positions(user_id=user_id)

    positions_value = 0.0
    for pos in held:
        price = cache.get_price(pos.ticker)
        if price is None:
            logger.debug(
                "Skipping snapshot: no price for held ticker %s", pos.ticker
            )
            return None
        positions_value += pos.quantity * price

    return snapshots_db.insert_snapshot(
        total_value=cash + positions_value, user_id=user_id
    )


async def _snapshot_loop(
    price_cache: PriceCache,
    interval: float,
    user_id: str,
) -> None:
    while True:
        try:
            await asyncio.sleep(interval)
            record_snapshot_now(price_cache, user_id=user_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Snapshot loop iteration failed; continuing")


async def start_snapshot_loop(
    price_cache: PriceCache | None = None,
    interval: float = DEFAULT_INTERVAL_SECONDS,
    user_id: str = DEFAULT_USER_ID,
) -> asyncio.Task[None]:
    """Launch the periodic snapshot task and return its asyncio.Task handle.

    Awaited by the FastAPI lifespan; the returned task is stashed on
    `state.snapshot_task` and cancelled on shutdown.
    """
    cache = price_cache if price_cache is not None else state.price_cache
    return asyncio.create_task(
        _snapshot_loop(cache, interval, user_id), name="portfolio-snapshot-loop"
    )

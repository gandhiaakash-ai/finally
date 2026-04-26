"""Shared application state holders.

The FastAPI lifespan populates these on startup so route handlers and
background tasks can reach them without import-time globals.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.market import MarketDataSource, PriceCache


@dataclass
class AppState:
    price_cache: PriceCache = field(default_factory=PriceCache)
    market_source: MarketDataSource | None = None
    snapshot_task: asyncio.Task[None] | None = None


state = AppState()

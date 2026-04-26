"""Fixtures for route-layer tests.

Provides a FastAPI TestClient backed by:
- a tmp SQLite DB (via FINALLY_DB_PATH),
- a freshly-built PriceCache pre-populated with seed prices,
- a fake MarketDataSource stub so watchlist add/remove succeed without spinning
  up the real simulator background task.

We deliberately bypass the production lifespan (which would launch the
simulator and snapshot loop) by using TestClient without entering it. Routes
read state from `app.state.state`, which we mutate directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.db import connection as conn_mod
from app.db import init_db
from app.market import MarketDataSource, PriceCache
from app.routes.portfolio import create_portfolio_router
from app.routes.watchlist import create_watchlist_router
from app.state import state


class StubMarketDataSource(MarketDataSource):
    """Records add/remove calls; never actually pushes prices."""

    def __init__(self) -> None:
        self._tickers: list[str] = []
        self.added: list[str] = []
        self.removed: list[str] = []

    async def start(self, tickers: list[str]) -> None:
        self._tickers = list(tickers)

    async def stop(self) -> None:
        pass

    async def add_ticker(self, ticker: str) -> None:
        ticker = ticker.upper()
        if ticker not in self._tickers:
            self._tickers.append(ticker)
        self.added.append(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper()
        if ticker in self._tickers:
            self._tickers.remove(ticker)
        self.removed.append(ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)


@pytest.fixture
def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "test.db"))
    conn_mod.reset_connection()
    init_db()

    cache = PriceCache()
    for ticker, price in {
        "AAPL": 200.0, "GOOGL": 175.0, "MSFT": 400.0, "AMZN": 185.0,
        "TSLA": 250.0, "NVDA": 800.0, "META": 500.0, "JPM": 195.0,
        "V": 280.0, "NFLX": 600.0,
    }.items():
        cache.update(ticker, price)

    stub = StubMarketDataSource()
    state.price_cache = cache
    state.market_source = stub

    app = FastAPI()
    api = APIRouter(prefix="/api")

    @api.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api)
    app.include_router(create_portfolio_router(cache))
    app.include_router(create_watchlist_router(cache, lambda: state.market_source))

    with TestClient(app) as client:
        yield client, cache, stub

    conn_mod.reset_connection()

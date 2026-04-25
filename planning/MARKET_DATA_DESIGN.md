# Market Data Backend — Detailed Design

Implementation-ready design for the FinAlly market data subsystem. This document
consolidates the unified interface, the GBM simulator, and the Massive API
client into a single blueprint with the code snippets needed to rebuild the
subsystem end-to-end.

All source lives under `backend/app/market/`. Downstream code (SSE, portfolio,
trade execution, chat) imports only from `app.market` — never from a submodule.

---

## Table of Contents

1. [Goals & Architecture](#1-goals--architecture)
2. [File Structure](#2-file-structure)
3. [Data Model — `models.py`](#3-data-model--modelspy)
4. [Price Cache — `cache.py`](#4-price-cache--cachepy)
5. [Abstract Interface — `interface.py`](#5-abstract-interface--interfacepy)
6. [Seed Prices & Parameters — `seed_prices.py`](#6-seed-prices--parameters--seed_pricespy)
7. [GBM Simulator — `simulator.py` (model)](#7-gbm-simulator--simulatorpy-model)
8. [SimulatorDataSource — `simulator.py` (async wrapper)](#8-simulatordatasource--simulatorpy-async-wrapper)
9. [Massive API Client — `massive_client.py`](#9-massive-api-client--massive_clientpy)
10. [Factory — `factory.py`](#10-factory--factorypy)
11. [SSE Streaming Endpoint — `stream.py`](#11-sse-streaming-endpoint--streampy)
12. [FastAPI Lifecycle Integration](#12-fastapi-lifecycle-integration)
13. [Testing Strategy](#13-testing-strategy)
14. [Configuration Summary](#14-configuration-summary)

---

## 1. Goals & Architecture

### Goals

- **One interface, two implementations.** Downstream code calls a single ABC.
  Swapping simulator for live data is a configuration change, not a code change.
- **Cache-centric.** Producers (simulator / Massive poller) write into a shared
  `PriceCache`. Consumers (SSE, portfolio, trades) read from it. Producers and
  consumers never talk to each other directly.
- **Async-first, lock-safe.** The producer loop runs as an asyncio task. The
  cache uses a `threading.Lock` so blocking calls (e.g., the synchronous
  Massive SDK invoked through `asyncio.to_thread`) are safe.
- **No defensive scaffolding.** Errors inside the producer loop are logged and
  the loop retries on the next tick. Errors are not propagated to the consumer
  side. We prefer obvious staleness over silent fakery.
- **Cheap to start, cheap to stop.** Both implementations expose the same
  `start / stop / add_ticker / remove_ticker / get_tickers` lifecycle.

### Architecture

```
                       ┌──────────────────────────────┐
                       │   MarketDataSource (ABC)     │
                       └──────────────┬───────────────┘
                                      │
              ┌───────────────────────┴────────────────────────┐
              ▼                                                ▼
   ┌────────────────────┐                          ┌──────────────────────┐
   │ SimulatorDataSource│                          │  MassiveDataSource   │
   │  (GBM, default)    │                          │  (Polygon REST poll) │
   └─────────┬──────────┘                          └──────────┬───────────┘
             │ writes                                          │ writes
             └────────────────┬───────────────────────────────┘
                              ▼
                    ┌──────────────────┐
                    │   PriceCache     │  thread-safe, version-counted
                    └────┬─────────┬───┘
                  reads  │         │  reads
                         ▼         ▼
                ┌──────────────┐  ┌──────────────────────────┐
                │ SSE endpoint │  │  Portfolio / Trade exec  │
                │ /api/stream  │  │  /api/portfolio/*        │
                └──────────────┘  └──────────────────────────┘
```

### Why these choices

| Decision | Rationale |
|---|---|
| Strategy pattern (ABC + two impls) | Factory selection is the only branch; downstream is source-agnostic. |
| `PriceCache` as single point of truth | Many consumers, one writer at a time. No fan-out logic in producers. |
| Version counter for SSE change detection | Avoids idle traffic — only push when something actually changed. |
| `threading.Lock` on the cache | Massive SDK is sync and runs in a thread; the cache must be safe from any thread. |
| GBM with Cholesky-correlated moves | Multiplicative — prices stay positive; sector co-movement looks real. |
| REST poll (not WebSocket) for Massive | Works on the free tier; one snapshot call covers all watched tickers. |
| SSE (not WebSocket) for the browser | One-way push is all we need; native `EventSource` reconnects for free. |

---

## 2. File Structure

```
backend/app/market/
├── __init__.py             # Public exports
├── models.py               # PriceUpdate dataclass
├── cache.py                # PriceCache (thread-safe, version-counted)
├── interface.py            # MarketDataSource ABC
├── seed_prices.py          # Seed prices, GBM params, correlation groups
├── simulator.py            # GBMSimulator + SimulatorDataSource
├── massive_client.py       # MassiveDataSource (Polygon REST poller)
├── factory.py              # create_market_data_source()
└── stream.py               # SSE endpoint factory
```

Each file has a single responsibility. The public surface is re-exported by
`__init__.py`:

```python
# backend/app/market/__init__.py
"""Market data subsystem for FinAlly."""

from .cache import PriceCache
from .factory import create_market_data_source
from .interface import MarketDataSource
from .models import PriceUpdate
from .stream import create_stream_router

__all__ = [
    "PriceUpdate",
    "PriceCache",
    "MarketDataSource",
    "create_market_data_source",
    "create_stream_router",
]
```

### `pyproject.toml` essentials

```toml
[project]
name = "finally-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "numpy>=2.0",
    "massive>=0.1",            # formerly polygon-api-client
    "litellm>=1.50",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "ruff>=0.6",
    "rich>=13.0",
]

[tool.hatch.build.targets.wheel]
packages = ["app"]
```

---

## 3. Data Model — `models.py`

`PriceUpdate` is the only data structure that leaves the market data layer.
SSE serialization, portfolio valuation, and trade execution all consume it.

```python
# backend/app/market/models.py
"""Data models for market data."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PriceUpdate:
    """Immutable snapshot of a single ticker's price at a point in time."""

    ticker: str
    price: float
    previous_price: float
    timestamp: float = field(default_factory=time.time)  # Unix seconds

    @property
    def change(self) -> float:
        """Absolute price change from previous update."""
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
        """Percentage change from previous update."""
        if self.previous_price == 0:
            return 0.0
        return round((self.price - self.previous_price) / self.previous_price * 100, 4)

    @property
    def direction(self) -> str:
        """'up', 'down', or 'flat'."""
        if self.price > self.previous_price:
            return "up"
        elif self.price < self.previous_price:
            return "down"
        return "flat"

    def to_dict(self) -> dict:
        """Serialize for JSON / SSE transmission."""
        return {
            "ticker": self.ticker,
            "price": self.price,
            "previous_price": self.previous_price,
            "timestamp": self.timestamp,
            "change": self.change,
            "change_percent": self.change_percent,
            "direction": self.direction,
        }
```

### Notes

- `frozen=True` — hashable, never mutated after construction. We always
  replace, never edit.
- `previous_price` is the *previous cached price for this ticker*, not the
  previous trading day's close. Day-over-day change should be computed from
  Massive's `snap.day.previous_close` if needed.
- Timestamps are Unix **seconds** throughout. Sources that produce
  milliseconds (e.g., Massive) convert at their boundary.
- `change` is rounded to 4 dp — enough precision for sub-cent moves while
  keeping the JSON payload tidy.

---

## 4. Price Cache — `cache.py`

Thread-safe in-memory store. Producers write; SSE / portfolio / trade
execution all read.

```python
# backend/app/market/cache.py
"""Thread-safe in-memory price cache."""

from __future__ import annotations

import time
from threading import Lock

from .models import PriceUpdate


class PriceCache:
    """Thread-safe in-memory cache of the latest price for each ticker.

    Writers: SimulatorDataSource or MassiveDataSource (one at a time).
    Readers: SSE streaming endpoint, portfolio valuation, trade execution.
    """

    def __init__(self) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._lock = Lock()
        self._version: int = 0  # Monotonically increasing; bumped on every update

    def update(
        self,
        ticker: str,
        price: float,
        timestamp: float | None = None,
    ) -> PriceUpdate:
        """Record a new price for a ticker. Returns the created PriceUpdate.

        On first write for a ticker, previous_price == price (direction='flat').
        Prices are rounded to 2 dp at the cache boundary; producers may pass
        full-precision floats.
        """
        with self._lock:
            ts = timestamp or time.time()
            prev = self._prices.get(ticker)
            previous_price = prev.price if prev else price

            update = PriceUpdate(
                ticker=ticker,
                price=round(price, 2),
                previous_price=round(previous_price, 2),
                timestamp=ts,
            )
            self._prices[ticker] = update
            self._version += 1
            return update

    def get(self, ticker: str) -> PriceUpdate | None:
        with self._lock:
            return self._prices.get(ticker)

    def get_all(self) -> dict[str, PriceUpdate]:
        """Snapshot of all current prices. Returns a shallow copy."""
        with self._lock:
            return dict(self._prices)

    def get_price(self, ticker: str) -> float | None:
        update = self.get(ticker)
        return update.price if update else None

    def remove(self, ticker: str) -> None:
        """Remove a ticker (e.g., when removed from watchlist)."""
        with self._lock:
            self._prices.pop(ticker, None)

    @property
    def version(self) -> int:
        """Monotonic counter, +1 per update. Used by SSE for change detection."""
        return self._version

    def __len__(self) -> int:
        with self._lock:
            return len(self._prices)

    def __contains__(self, ticker: str) -> bool:
        with self._lock:
            return ticker in self._prices
```

### Key behaviours

- **First write semantics** — `previous_price == price`, `direction == "flat"`.
  Avoids a phantom up/down arrow on initial load.
- **Rounding to 2 dp** happens once, here. Keeps the rest of the system honest.
- **`version`** — monotonic counter. SSE polls it as a cheap change-detection
  signal so we never push when nothing has changed.
- **Locking** — single `threading.Lock`. The cache is small (one entry per
  ticker, ~50 entries max), the lock is held for microseconds.
- **`remove()`** — clears one ticker. Called when a ticker leaves the
  watchlist, so its row immediately disappears from SSE payloads.

The cache is created once at app startup and lives for the process lifetime.

---

## 5. Abstract Interface — `interface.py`

```python
# backend/app/market/interface.py
"""Abstract interface for market data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod


class MarketDataSource(ABC):
    """Contract for market data providers.

    Implementations push price updates into a shared PriceCache on their own
    schedule. Downstream code never calls the data source directly for prices —
    it reads from the cache.

    Lifecycle:
        source = create_market_data_source(cache)
        await source.start(["AAPL", "GOOGL", ...])
        # ... app runs ...
        await source.add_ticker("TSLA")
        await source.remove_ticker("GOOGL")
        # ... app shutting down ...
        await source.stop()
    """

    @abstractmethod
    async def start(self, tickers: list[str]) -> None:
        """Begin producing price updates for the given tickers.

        Spawns a background task that periodically writes to the PriceCache.
        Must be called exactly once. Calling start() twice is undefined.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Stop the background task and release resources.

        Safe to call multiple times. After stop(), the source will not write
        to the cache again.
        """

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Add a ticker to the active set. Idempotent."""

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker. Idempotent. Also removes it from the PriceCache."""

    @abstractmethod
    def get_tickers(self) -> list[str]:
        """Return the current list of actively tracked tickers."""
```

### Lifecycle contract

```
create_market_data_source(cache)         # constructed, not started
    → await source.start([...])          # spawns the background task; once
    → await source.add_ticker("TSLA")    # idempotent
    → await source.remove_ticker("...")  # idempotent
    → await source.stop()                # idempotent; safe to call twice
```

The source **does not return prices**. It pushes into the cache. Reading
prices is the cache's job.

---

## 6. Seed Prices & Parameters — `seed_prices.py`

Pure constants. Tweaks (a new ticker's vol, a new sector grouping) are
one-line changes that don't touch model code.

```python
# backend/app/market/seed_prices.py
"""Seed prices and per-ticker parameters for the market simulator."""

# Realistic starting prices for the default watchlist
SEED_PRICES: dict[str, float] = {
    "AAPL": 190.00,
    "GOOGL": 175.00,
    "MSFT": 420.00,
    "AMZN": 185.00,
    "TSLA": 250.00,
    "NVDA": 800.00,
    "META": 500.00,
    "JPM": 195.00,
    "V": 280.00,
    "NFLX": 600.00,
}

# Per-ticker GBM parameters
# sigma: annualized volatility (higher = more wiggle)
# mu: annualized drift / expected return
TICKER_PARAMS: dict[str, dict[str, float]] = {
    "AAPL":  {"sigma": 0.22, "mu": 0.05},
    "GOOGL": {"sigma": 0.25, "mu": 0.05},
    "MSFT":  {"sigma": 0.20, "mu": 0.05},
    "AMZN":  {"sigma": 0.28, "mu": 0.05},
    "TSLA":  {"sigma": 0.50, "mu": 0.03},  # High vol, modest drift
    "NVDA":  {"sigma": 0.40, "mu": 0.08},  # High vol, strong drift
    "META":  {"sigma": 0.30, "mu": 0.05},
    "JPM":   {"sigma": 0.18, "mu": 0.04},  # Calm bank
    "V":     {"sigma": 0.17, "mu": 0.04},  # Calm payments
    "NFLX":  {"sigma": 0.35, "mu": 0.05},
}

# Fallback for unknown / dynamically added tickers
DEFAULT_PARAMS: dict[str, float] = {"sigma": 0.25, "mu": 0.05}

# Correlation groups: tickers in the same group move together
CORRELATION_GROUPS: dict[str, set[str]] = {
    "tech":    {"AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "NFLX"},
    "finance": {"JPM", "V"},
}

# Correlation coefficients
INTRA_TECH_CORR    = 0.6   # within tech
INTRA_FINANCE_CORR = 0.5   # within finance
CROSS_GROUP_CORR   = 0.3   # cross-sector / unknown tickers
TSLA_CORR          = 0.3   # TSLA does its own thing
```

### Notes

- `TSLA` is in the `tech` set but its pairwise correlation is forced to 0.3.
  Visible divergence makes the dashboard more interesting.
- Tickers added at runtime that aren't in `SEED_PRICES` get a random starting
  price in `[50, 300]` and the `DEFAULT_PARAMS`.
- The correlation rules above always yield a positive-semi-definite matrix,
  so `np.linalg.cholesky` never fails.

---

## 7. GBM Simulator — `simulator.py` (model)

Pure model — no asyncio, no I/O, no cache awareness. The async wrapper
(`SimulatorDataSource`) lives in the same file but is documented separately.

### The math

```
S(t + dt) = S(t) * exp((mu - 0.5 * sigma^2) * dt + sigma * sqrt(dt) * Z)
```

| Symbol | Meaning |
|--------|---------|
| `S(t)` | current price (seeded from `SEED_PRICES`) |
| `mu`   | annualized drift |
| `sigma`| annualized volatility |
| `dt`   | tick interval as a fraction of a trading year (~8.48e-8) |
| `Z`    | correlated standard normal draw |

#### Why `dt ≈ 8.5e-8`

We tick every 500 ms. A trading year is `252 days × 6.5 hours × 3600 s
= 5,896,800 seconds`. So `dt = 0.5 / 5_896_800 ≈ 8.48e-8`. This makes per-tick
moves sub-cent; daily volatility (~`sigma / sqrt(252)`) emerges naturally
from accumulating thousands of ticks.

#### Why GBM (not a plain random walk)

- Multiplicative through `exp(...)` — prices stay positive, no clipping.
- Lognormal returns match the actual statistical shape of real prices.
- Closed-form per step; one `np.exp` and one Cholesky multiply per tick.

#### Correlated moves via Cholesky

Given a positive-semi-definite correlation matrix `C`, compute
`L = cholesky(C)`. Then `Z_correlated = L @ Z_independent` produces a vector
of correlated normals with the desired correlation structure.

#### Random shocks

Plain GBM is realistic but visually monotonous. At every tick, per ticker:

```
P(shock) = event_probability                  (default 0.001)
shock_magnitude ~ Uniform(0.02, 0.05)         # 2–5%
shock_sign ∈ {-1, +1} uniformly
```

With 10 tickers ticking every 500 ms and `event_prob = 0.001`, expect a
shock somewhere on screen roughly every 50 seconds.

### The class

```python
# backend/app/market/simulator.py — top half
"""GBM-based market simulator."""

from __future__ import annotations

import asyncio
import logging
import math
import random

import numpy as np

from .cache import PriceCache
from .interface import MarketDataSource
from .seed_prices import (
    CORRELATION_GROUPS,
    CROSS_GROUP_CORR,
    DEFAULT_PARAMS,
    INTRA_FINANCE_CORR,
    INTRA_TECH_CORR,
    SEED_PRICES,
    TICKER_PARAMS,
    TSLA_CORR,
)

logger = logging.getLogger(__name__)


class GBMSimulator:
    """Geometric Brownian Motion simulator for correlated stock prices."""

    # 252 trading days * 6.5 hours/day * 3600 seconds/hour
    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600  # 5,896,800
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR  # ~8.48e-8

    def __init__(
        self,
        tickers: list[str],
        dt: float = DEFAULT_DT,
        event_probability: float = 0.001,
    ) -> None:
        self._dt = dt
        self._event_prob = event_probability

        self._tickers: list[str] = []
        self._prices: dict[str, float] = {}
        self._params: dict[str, dict[str, float]] = {}
        self._cholesky: np.ndarray | None = None

        for ticker in tickers:
            self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    # ----- Public API -----

    def step(self) -> dict[str, float]:
        """Advance all tickers by one time step. Returns {ticker: new_price}.

        Hot path — called every 500 ms.
        """
        n = len(self._tickers)
        if n == 0:
            return {}

        # 1. n independent standard normals
        z_independent = np.random.standard_normal(n)

        # 2. Apply Cholesky to get correlated draws (skip when n <= 1)
        if self._cholesky is not None:
            z_correlated = self._cholesky @ z_independent
        else:
            z_correlated = z_independent

        # 3. GBM step + optional shock per ticker
        result: dict[str, float] = {}
        for i, ticker in enumerate(self._tickers):
            params = self._params[ticker]
            mu = params["mu"]
            sigma = params["sigma"]

            drift = (mu - 0.5 * sigma ** 2) * self._dt
            diffusion = sigma * math.sqrt(self._dt) * z_correlated[i]
            self._prices[ticker] *= math.exp(drift + diffusion)

            if random.random() < self._event_prob:
                shock_magnitude = random.uniform(0.02, 0.05)
                shock_sign = random.choice([-1, 1])
                self._prices[ticker] *= 1 + shock_magnitude * shock_sign
                logger.debug(
                    "Random event on %s: %.1f%% %s",
                    ticker, shock_magnitude * 100,
                    "up" if shock_sign > 0 else "down",
                )

            result[ticker] = round(self._prices[ticker], 2)

        return result

    def add_ticker(self, ticker: str) -> None:
        """Add a ticker. Rebuilds the Cholesky decomposition."""
        if ticker in self._prices:
            return
        self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker. Rebuilds the Cholesky decomposition."""
        if ticker not in self._prices:
            return
        self._tickers.remove(ticker)
        del self._prices[ticker]
        del self._params[ticker]
        self._rebuild_cholesky()

    def get_price(self, ticker: str) -> float | None:
        return self._prices.get(ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    # ----- Internals -----

    def _add_ticker_internal(self, ticker: str) -> None:
        """Add a ticker without rebuilding Cholesky (batch initialization)."""
        if ticker in self._prices:
            return
        self._tickers.append(ticker)
        self._prices[ticker] = SEED_PRICES.get(ticker, random.uniform(50.0, 300.0))
        self._params[ticker] = TICKER_PARAMS.get(ticker, dict(DEFAULT_PARAMS))

    def _rebuild_cholesky(self) -> None:
        """Rebuild the Cholesky decomposition. Called on add/remove."""
        n = len(self._tickers)
        if n <= 1:
            self._cholesky = None
            return

        corr = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                rho = self._pairwise_correlation(self._tickers[i], self._tickers[j])
                corr[i, j] = rho
                corr[j, i] = rho

        self._cholesky = np.linalg.cholesky(corr)

    @staticmethod
    def _pairwise_correlation(t1: str, t2: str) -> float:
        """Determine correlation between two tickers based on sector grouping."""
        tech = CORRELATION_GROUPS["tech"]
        finance = CORRELATION_GROUPS["finance"]

        # TSLA is in tech but behaves independently
        if t1 == "TSLA" or t2 == "TSLA":
            return TSLA_CORR
        if t1 in tech and t2 in tech:
            return INTRA_TECH_CORR
        if t1 in finance and t2 in finance:
            return INTRA_FINANCE_CORR
        return CROSS_GROUP_CORR
```

### Behavioural properties (hold by construction)

- **Prices stay positive.** GBM is multiplicative; `exp(...) > 0` always.
- **Mean-reverting in the short term, drifting in the long term.** Per-tick
  moves are dominated by diffusion; over thousands of ticks, drift wins.
- **Correlation is symmetric and bounded** in `[0.3, 0.6]`. Cholesky always
  succeeds.
- **First tick after `add_ticker`** is uncorrelated with prior history (the
  Cholesky matrix is rebuilt fresh).
- **Removing a ticker** removes its row/column and re-decomposes — other
  tickers are unaffected.
- **Reproducible** — `random.seed(...)` and `np.random.seed(...)` give the
  same path.

### What the simulator deliberately does *not* do

- No order book, bid/ask, or microstructure.
- No after-hours / pre-market sessions — runs continuously.
- No fundamentals, splits, dividends, or earnings.
- No regime changes — drift is constant per ticker for the session.

---

## 8. SimulatorDataSource — `simulator.py` (async wrapper)

Wraps `GBMSimulator` in an asyncio loop and conforms to `MarketDataSource`.

```python
# backend/app/market/simulator.py — bottom half

class SimulatorDataSource(MarketDataSource):
    """MarketDataSource backed by the GBM simulator.

    Runs a background asyncio task that calls GBMSimulator.step() every
    `update_interval` seconds and writes results to the PriceCache.
    """

    def __init__(
        self,
        price_cache: PriceCache,
        update_interval: float = 0.5,
        event_probability: float = 0.001,
    ) -> None:
        self._cache = price_cache
        self._interval = update_interval
        self._event_prob = event_probability
        self._sim: GBMSimulator | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._sim = GBMSimulator(
            tickers=tickers,
            event_probability=self._event_prob,
        )
        # Seed the cache with starting prices so SSE has data immediately
        for ticker in tickers:
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker=ticker, price=price)
        self._task = asyncio.create_task(self._run_loop(), name="simulator-loop")
        logger.info("Simulator started with %d tickers", len(tickers))

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Simulator stopped")

    async def add_ticker(self, ticker: str) -> None:
        if self._sim:
            self._sim.add_ticker(ticker)
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker=ticker, price=price)
            logger.info("Simulator: added ticker %s", ticker)

    async def remove_ticker(self, ticker: str) -> None:
        if self._sim:
            self._sim.remove_ticker(ticker)
        self._cache.remove(ticker)
        logger.info("Simulator: removed ticker %s", ticker)

    def get_tickers(self) -> list[str]:
        return self._sim.get_tickers() if self._sim else []

    async def _run_loop(self) -> None:
        """Core loop: step the simulation, write to cache, sleep."""
        while True:
            try:
                if self._sim:
                    prices = self._sim.step()
                    for ticker, price in prices.items():
                        self._cache.update(ticker=ticker, price=price)
            except Exception:
                logger.exception("Simulator step failed")
            await asyncio.sleep(self._interval)
```

### Tunables

| Param | Default | Meaning |
|-------|---------|---------|
| `update_interval` | `0.5` s | How often `step()` runs |
| `event_probability` | `0.001` | Per-tick chance of a 2–5% shock per ticker |

### Lifecycle behaviour

- `start()` is called exactly once. It (1) constructs the simulator,
  (2) **seeds the cache immediately** so SSE clients connecting in the first
  500 ms get data, and (3) spawns the background task.
- `stop()` cancels the task, awaits it, swallows `CancelledError`. Safe to
  call twice.
- `add_ticker` is idempotent: it adds to the simulator AND seeds the cache so
  the new ticker has a price before the next tick.
- A single bad tick must not kill the simulator — the broad `except` in
  `_run_loop` catches and logs, then the loop sleeps and retries.

---

## 9. Massive API Client — `massive_client.py`

Polls Massive's snapshot endpoint for all watched tickers in **a single
call** and writes to the shared cache.

### Quick facts

| Item | Value |
|------|-------|
| Package | `massive` (PyPI; rename of `polygon-api-client`) |
| Install | `uv add massive` |
| Auth | API key via `RESTClient(api_key=...)` (or `MASSIVE_API_KEY` env) |
| SDK style | Synchronous → wrapped in `asyncio.to_thread` |

### Rate limits & poll cadence

| Tier | Limit | Poll interval |
|------|-------|---------------|
| Free | 5 req/min | 15 s (default) |
| Starter | 100 req/min | 5 s |
| Developer+ | Unlimited (~100 req/s soft cap) | 2 s |

Because we batch all watched tickers into one snapshot call, **one poll =
one request**, regardless of watchlist size.

### Endpoint we use

`GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,GOOGL,...`
via `client.get_snapshot_all(market_type=..., tickers=[...])`.

Each snapshot exposes — fields we read are bolded:

| Path | Type | Notes |
|------|------|-------|
| **`snap.ticker`** | `str` | Ticker symbol |
| **`snap.last_trade.price`** | `float` | Most recent traded price (we cache this) |
| **`snap.last_trade.timestamp`** | `int` | Unix **milliseconds** (÷1000) |
| `snap.last_quote.bid_price / ask_price` | `float` | NBBO |
| `snap.day.{open,high,low,close,volume}` | nested | Today's session |
| `snap.day.previous_close` | `float` | Prior session close |
| `snap.todays_change_perc` | `float` | Pre-computed day change % |

### The class

```python
# backend/app/market/massive_client.py
"""Massive (Polygon.io) API client for real market data."""

from __future__ import annotations

import asyncio
import logging

from massive import RESTClient
from massive.rest.models import SnapshotMarketType

from .cache import PriceCache
from .interface import MarketDataSource

logger = logging.getLogger(__name__)


class MassiveDataSource(MarketDataSource):
    """MarketDataSource backed by the Massive (Polygon.io) REST API.

    Polls GET /v2/snapshot/locale/us/markets/stocks/tickers for all watched
    tickers in a single API call, then writes results to the PriceCache.

    Rate limits:
      - Free tier: 5 req/min  → poll every 15s (default)
      - Paid tiers: higher    → poll every 2-5s
    """

    def __init__(
        self,
        api_key: str,
        price_cache: PriceCache,
        poll_interval: float = 15.0,
    ) -> None:
        self._api_key = api_key
        self._cache = price_cache
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None
        self._client: RESTClient | None = None

    async def start(self, tickers: list[str]) -> None:
        self._client = RESTClient(api_key=self._api_key)
        self._tickers = list(tickers)

        # Immediate first poll so the cache has data right away
        await self._poll_once()

        self._task = asyncio.create_task(self._poll_loop(), name="massive-poller")
        logger.info(
            "Massive poller started: %d tickers, %.1fs interval",
            len(tickers),
            self._interval,
        )

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._client = None
        logger.info("Massive poller stopped")

    async def add_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        if ticker not in self._tickers:
            self._tickers.append(ticker)
            logger.info("Massive: added ticker %s (will appear on next poll)", ticker)

    async def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        self._tickers = [t for t in self._tickers if t != ticker]
        self._cache.remove(ticker)
        logger.info("Massive: removed ticker %s", ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    # ----- Internal -----

    async def _poll_loop(self) -> None:
        """Poll on interval. First poll already happened in start()."""
        while True:
            await asyncio.sleep(self._interval)
            await self._poll_once()

    async def _poll_once(self) -> None:
        """Execute one poll cycle: fetch snapshots, update cache."""
        if not self._tickers or not self._client:
            return

        try:
            # The Massive RESTClient is sync — run in a thread so we don't
            # block the asyncio loop.
            snapshots = await asyncio.to_thread(self._fetch_snapshots)
            processed = 0
            for snap in snapshots:
                try:
                    price = snap.last_trade.price
                    # Massive timestamps are Unix ms; cache speaks seconds
                    timestamp = snap.last_trade.timestamp / 1000.0
                    self._cache.update(
                        ticker=snap.ticker,
                        price=price,
                        timestamp=timestamp,
                    )
                    processed += 1
                except (AttributeError, TypeError) as e:
                    logger.warning(
                        "Skipping snapshot for %s: %s",
                        getattr(snap, "ticker", "???"),
                        e,
                    )
            logger.debug(
                "Massive poll: updated %d/%d tickers",
                processed,
                len(self._tickers),
            )
        except Exception as e:
            logger.error("Massive poll failed: %s", e)
            # Don't re-raise — the loop retries on the next interval.
            # Common failures: 401 (bad key), 429 (rate limit), network.

    def _fetch_snapshots(self) -> list:
        """Synchronous call to the Massive REST API. Runs in a thread."""
        return self._client.get_snapshot_all(
            market_type=SnapshotMarketType.STOCKS,
            tickers=self._tickers,
        )
```

### Error modes

| HTTP | Meaning | Behaviour |
|------|---------|-----------|
| 401 | Bad / missing API key | Logged; loop continues. Operator should fix `MASSIVE_API_KEY`. |
| 403 | Plan does not include endpoint | Same — surface in logs, keep running. |
| 429 | Rate limit exceeded | Logged; next poll waits one interval. Increase interval if frequent. |
| 5xx | Massive server error | SDK retries 3× internally with backoff; we log and wait. |
| Network / DNS | Connection error | Same as 5xx. |

We deliberately do **not** auto-fall-back to the simulator on failure. The
cache simply goes stale (SSE stops emitting changes) until the API recovers.
Stale prices are clearly visible; silent fakery would be worse.

### Gotchas

- The `tickers=` parameter on `get_snapshot_all` is what makes one poll cover
  the whole watchlist. Without it the call returns *all* US equities (~10k).
- Some plans return `last_trade.price == 0` for thinly traded symbols outside
  market hours. Filter or fall back to `day.close` if observed.
- The free tier serves prices on a **15-minute delay**. Real-time access
  requires a paid plan — the simulator is a better demo experience than
  15-min-delayed real data.
- `polygon-api-client` and `massive` are interchangeable; only the import
  changes.

---

## 10. Factory — `factory.py`

```python
# backend/app/market/factory.py
"""Factory for creating market data sources."""

from __future__ import annotations

import logging
import os

from .cache import PriceCache
from .interface import MarketDataSource
from .massive_client import MassiveDataSource
from .simulator import SimulatorDataSource

logger = logging.getLogger(__name__)


def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    """Create the appropriate market data source based on environment variables.

    - MASSIVE_API_KEY set and non-empty → MassiveDataSource (real data)
    - Otherwise → SimulatorDataSource (GBM simulation)

    Returns an unstarted source. Caller must await source.start(tickers).
    """
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()

    if api_key:
        logger.info("Market data source: Massive API (real data)")
        return MassiveDataSource(api_key=api_key, price_cache=price_cache)
    else:
        logger.info("Market data source: GBM Simulator")
        return SimulatorDataSource(price_cache=price_cache)
```

Selection rules:

- `MASSIVE_API_KEY` set and non-empty → `MassiveDataSource` (real data).
- Otherwise → `SimulatorDataSource` (GBM simulation).
- No auto-fallback. If the Massive API fails at runtime, the simulator is
  **not** swapped in.

---

## 11. SSE Streaming Endpoint — `stream.py`

The consumer side. Reads from the cache, pushes Server-Sent Events to the
browser. Uses the version counter for change detection so an idle market
produces no traffic.

```python
# backend/app/market/stream.py
"""SSE streaming endpoint for live price updates."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stream", tags=["streaming"])


def create_stream_router(price_cache: PriceCache) -> APIRouter:
    """Create the SSE streaming router with a reference to the price cache.

    Factory pattern lets us inject the cache without globals.
    """

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        """SSE endpoint for live price updates.

        Streams all tracked ticker prices every ~500ms whenever the cache
        version changes. The client connects with EventSource and receives
        events of shape:

            data: {"AAPL": {"ticker": "AAPL", "price": 190.50, ...}, ...}

        Includes a retry directive so the browser auto-reconnects on
        disconnection (EventSource built-in behavior).
        """
        return StreamingResponse(
            _generate_events(price_cache, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering if proxied
            },
        )

    return router


async def _generate_events(
    price_cache: PriceCache,
    request: Request,
    interval: float = 0.5,
) -> AsyncGenerator[str, None]:
    """Async generator yielding SSE-formatted price events.

    Polls the cache version every `interval` seconds; emits only when a
    new version is observed. Stops cleanly on client disconnect.
    """
    yield "retry: 1000\n\n"  # browser reconnects after 1 s on drop

    last_version = -1
    client_ip = request.client.host if request.client else "unknown"
    logger.info("SSE client connected: %s", client_ip)

    try:
        while True:
            if await request.is_disconnected():
                logger.info("SSE client disconnected: %s", client_ip)
                break

            current_version = price_cache.version
            if current_version != last_version:
                last_version = current_version
                prices = price_cache.get_all()

                if prices:
                    data = {
                        ticker: update.to_dict()
                        for ticker, update in prices.items()
                    }
                    payload = json.dumps(data)
                    yield f"data: {payload}\n\n"

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("SSE stream cancelled for: %s", client_ip)
```

### Mechanics

- Subscribes by polling `price_cache.version` at 500 ms — cheap (one int
  read under the lock).
- Only emits when `version` changes (no idle traffic).
- Sends `retry: 1000` so the browser's `EventSource` reconnects after 1 s.
- Uses `request.is_disconnected()` to detect client departure and break out.
- `X-Accel-Buffering: no` keeps nginx (if proxied) from buffering the stream.
- Payload shape (one event per change):

  ```
  data: {"AAPL": {"ticker": "AAPL", "price": 190.52,
                  "previous_price": 190.50, "timestamp": 1714060800.123,
                  "change": 0.02, "change_percent": 0.0105,
                  "direction": "up"}, ...}\n\n
  ```

This decoupling — cache as the single point of truth — means many concurrent
SSE clients impose zero extra load on the data source.

### Frontend consumption

```ts
const es = new EventSource("/api/stream/prices");
es.onmessage = (e) => {
  const updates = JSON.parse(e.data) as Record<string, PriceUpdate>;
  for (const [ticker, u] of Object.entries(updates)) {
    applyTick(ticker, u);  // flash green/red, update sparkline, etc.
  }
};
// EventSource handles reconnection automatically
```

---

## 12. FastAPI Lifecycle Integration

### Startup / shutdown

```python
# backend/app/main.py (excerpt)
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.market import (
    PriceCache,
    create_market_data_source,
    create_stream_router,
)

DEFAULT_TICKERS = [
    "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
    "NVDA", "META", "JPM", "V", "NFLX",
]

price_cache = PriceCache()
market_source = create_market_data_source(price_cache)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    initial_tickers = await load_watchlist_from_db()  # falls back to DEFAULT_TICKERS
    await market_source.start(initial_tickers or DEFAULT_TICKERS)
    try:
        yield
    finally:
        # Shutdown
        await market_source.stop()


app = FastAPI(lifespan=lifespan)
app.include_router(create_stream_router(price_cache))
```

### Watchlist coordination

When the user (or the LLM) adds or removes a ticker, the API route updates
both the database and the running market source so the next tick reflects
the change.

```python
# backend/app/api/watchlist.py (excerpt)
@router.post("/api/watchlist")
async def add_to_watchlist(req: AddTickerRequest):
    ticker = req.ticker.upper().strip()
    await db.insert_watchlist_entry(user_id="default", ticker=ticker)
    await market_source.add_ticker(ticker)
    return {"ok": True}


@router.delete("/api/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str):
    ticker = ticker.upper().strip()
    await db.delete_watchlist_entry(user_id="default", ticker=ticker)
    await market_source.remove_ticker(ticker)
    return {"ok": True}
```

### Reading prices for trade execution

```python
# backend/app/api/portfolio.py (excerpt)
@router.post("/api/portfolio/trade")
async def execute_trade(trade: TradeRequest):
    ticker = trade.ticker.upper().strip()
    update = price_cache.get(ticker)
    if update is None:
        raise HTTPException(503, f"Price for {ticker} not yet available")

    fill_price = update.price
    # ... validation, DB writes, snapshot recording ...
    return {"executed_at_price": fill_price}
```

---

## 13. Testing Strategy

Tests live in `backend/tests/market/`. Run with `uv run --extra dev pytest -v`.

| File | Coverage |
|------|----------|
| `test_models.py` | `PriceUpdate` immutability, properties, `to_dict()` |
| `test_cache.py` | First-write semantics, version counter, threading, removal |
| `test_simulator.py` | GBM math, correlation matrix shape, add/remove, shocks |
| `test_simulator_source.py` | Lifecycle: `start → tick → cache populated → stop` |
| `test_massive.py` | Poller behaviour with the SDK mocked at the import boundary |
| `test_factory.py` | Env-driven selection between simulator and Massive |

### Example: cache first-write semantics

```python
# tests/market/test_cache.py
def test_first_write_has_flat_direction():
    cache = PriceCache()
    update = cache.update("AAPL", 190.0)
    assert update.previous_price == update.price
    assert update.direction == "flat"
    assert cache.version == 1

def test_subsequent_write_records_previous_price():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    update = cache.update("AAPL", 190.50)
    assert update.previous_price == 190.0
    assert update.direction == "up"
    assert cache.version == 2
```

### Example: simulator GBM math

```python
# tests/market/test_simulator.py
import math
import random

import numpy as np


def test_step_returns_positive_prices():
    sim = GBMSimulator(["AAPL", "GOOGL", "MSFT"])
    for _ in range(1000):
        prices = sim.step()
        assert all(p > 0 for p in prices.values())


def test_seeded_runs_are_deterministic():
    random.seed(42)
    np.random.seed(42)
    sim_a = GBMSimulator(["AAPL", "GOOGL"])
    seq_a = [sim_a.step() for _ in range(5)]

    random.seed(42)
    np.random.seed(42)
    sim_b = GBMSimulator(["AAPL", "GOOGL"])
    seq_b = [sim_b.step() for _ in range(5)]

    assert seq_a == seq_b
```

### Example: Massive poller mocked

```python
# tests/market/test_massive.py
from unittest.mock import MagicMock, patch
import pytest


@pytest.mark.asyncio
async def test_poll_writes_cache_with_seconds_timestamp():
    cache = PriceCache()
    source = MassiveDataSource(api_key="test", price_cache=cache)
    source._client = MagicMock()
    source._tickers = ["AAPL"]

    fake_snap = MagicMock()
    fake_snap.ticker = "AAPL"
    fake_snap.last_trade.price = 190.50
    fake_snap.last_trade.timestamp = 1_714_060_800_000  # ms

    with patch.object(source, "_fetch_snapshots", return_value=[fake_snap]):
        await source._poll_once()

    update = cache.get("AAPL")
    assert update.price == 190.50
    assert update.timestamp == 1_714_060_800.0  # converted to seconds
```

### Example: factory selection

```python
# tests/market/test_factory.py
import os
from unittest.mock import patch


def test_factory_returns_simulator_when_no_key():
    cache = PriceCache()
    with patch.dict(os.environ, {"MASSIVE_API_KEY": ""}, clear=False):
        source = create_market_data_source(cache)
    assert isinstance(source, SimulatorDataSource)


def test_factory_returns_massive_when_key_set():
    cache = PriceCache()
    with patch.dict(os.environ, {"MASSIVE_API_KEY": "abc123"}, clear=False):
        source = create_market_data_source(cache)
    assert isinstance(source, MassiveDataSource)
```

The contract — that both sources implement the ABC and write `PriceUpdate`s
into the cache — is what consumers depend on. As long as that holds, the
simulator is a faithful stand-in for the real API in tests, demos, and CI.

---

## 14. Configuration Summary

### Environment variables

| Var | Required? | Default | Effect |
|-----|-----------|---------|--------|
| `MASSIVE_API_KEY` | optional | unset | If set/non-empty → use Massive. Else simulator. |
| `OPENROUTER_API_KEY` | required | — | Unrelated to market data; used by chat. |
| `LLM_MOCK` | optional | `false` | Unrelated; mock LLM responses for tests. |

### Tunables exposed to constructors

| Class | Param | Default | Notes |
|-------|-------|---------|-------|
| `SimulatorDataSource` | `update_interval` | `0.5` s | Tick cadence |
| `SimulatorDataSource` | `event_probability` | `0.001` | Per-tick shock chance |
| `GBMSimulator` | `dt` | `~8.48e-8` | Trading-year fraction |
| `MassiveDataSource` | `poll_interval` | `15.0` s | Free-tier safe |
| SSE `_generate_events` | `interval` | `0.5` s | Cache-version poll |

### Default watchlist

`AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX` — seed prices and
GBM parameters live in `seed_prices.py`.

### Public import surface

```python
from app.market import (
    PriceUpdate,            # immutable price snapshot
    PriceCache,             # in-memory store
    MarketDataSource,       # ABC
    create_market_data_source,  # factory
    create_stream_router,   # FastAPI router for SSE
)
```

That's the whole contract. Everything else under `app.market.*` is
implementation detail.

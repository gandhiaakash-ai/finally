# Market Data Interface

Unified Python interface for live market data in FinAlly. Two implementations sit behind one abstract class — a simulator (default) and the Massive API client (when `MASSIVE_API_KEY` is set). Everything downstream reads through a single in‑memory cache and never knows which source produced the data.

The interface is implemented in `backend/app/market/`. This document is the design contract.

---

## 1. Design Principles

1. **One interface, two implementations.** Downstream code calls a single ABC. Swapping simulator for live data is a configuration change, not a code change.
2. **Cache‑centric.** Producers (simulator / Massive poller) write into a shared `PriceCache`. Consumers (SSE, portfolio, trades) read from it. The producers and consumers never talk to each other directly.
3. **Async‑first, lock‑safe.** The producer loop runs as an asyncio task. The cache uses a `threading.Lock` so blocking calls running in `asyncio.to_thread` are safe.
4. **No defensive scaffolding.** Errors inside the producer loop are logged and the loop retries on the next tick. Errors are not propagated to the consumer side.
5. **Cheap to start, cheap to stop.** Both implementations expose the same `start / stop / add_ticker / remove_ticker` lifecycle.

---

## 2. Module Layout

```
backend/app/market/
├── __init__.py           # Public exports
├── models.py             # PriceUpdate dataclass
├── cache.py              # PriceCache (thread-safe, version-counted)
├── interface.py          # MarketDataSource (ABC)
├── factory.py            # create_market_data_source()
├── simulator.py          # GBMSimulator + SimulatorDataSource
├── massive_client.py     # MassiveDataSource (Polygon REST poller)
├── seed_prices.py        # Constants: seed prices, GBM params, correlation groups
└── stream.py             # SSE endpoint factory (consumer-side)
```

Public surface (`from app.market import …`):

```python
PriceUpdate            # immutable price snapshot
PriceCache             # in-memory store (writers and readers share)
MarketDataSource       # ABC implemented by Simulator / Massive
create_market_data_source(cache)   # factory — picks based on env
create_stream_router(cache)        # FastAPI router for /api/stream/prices
```

---

## 3. Core Data Model — `PriceUpdate`

A frozen, immutable dataclass. The only data structure that crosses the market boundary.

```python
@dataclass(frozen=True, slots=True)
class PriceUpdate:
    ticker: str
    price: float
    previous_price: float
    timestamp: float = field(default_factory=time.time)  # Unix seconds

    @property
    def change(self) -> float: ...           # price - previous_price
    @property
    def change_percent(self) -> float: ...   # rounded to 4 dp
    @property
    def direction(self) -> str: ...          # "up" | "down" | "flat"

    def to_dict(self) -> dict: ...           # for JSON / SSE serialization
```

Notes:
- `frozen=True` means it's hashable and never mutated after construction; we always replace, never edit.
- `previous_price` is the *previous cached price for this ticker*, not the previous trading day's close. (For day‑over‑day change use the Massive snapshot's `day.previous_close` separately if needed.)
- Timestamps are Unix seconds throughout. Sources that produce milliseconds must convert at their boundary.

---

## 4. PriceCache

Thread‑safe in‑memory store. Producer writes; SSE / portfolio / trade execution all read.

```python
class PriceCache:
    def update(self, ticker: str, price: float, timestamp: float | None = None) -> PriceUpdate: ...
    def get(self, ticker: str) -> PriceUpdate | None: ...
    def get_all(self) -> dict[str, PriceUpdate]: ...
    def get_price(self, ticker: str) -> float | None: ...
    def remove(self, ticker: str) -> None: ...

    @property
    def version(self) -> int: ...   # monotonic counter, +1 per update
```

Key behaviours:

- **First write of a ticker** — `previous_price == price`, `direction == "flat"`. Avoids a phantom up/down on initialisation.
- **Prices are rounded to 2 dp** at write time. The cache is the only place this happens; producers may pass full‑precision floats.
- **`version`** — monotonic counter incremented on every `update()`. SSE uses it as a change‑detection signal so we only push when something actually changed.
- **Locking** — single `threading.Lock` around all reads and writes. The lock is fine‑grained (microseconds held) and the cache itself is small (one entry per ticker).
- **`remove()`** — clears one ticker. Called when a ticker leaves the watchlist.

The cache is created once at app startup and lives for the process lifetime.

---

## 5. The Abstract Source — `MarketDataSource`

```python
class MarketDataSource(ABC):
    @abstractmethod
    async def start(self, tickers: list[str]) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None: ...

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None: ...

    @abstractmethod
    def get_tickers(self) -> list[str]: ...
```

Lifecycle contract:

```
create_market_data_source(cache)         # constructed, not started
    → await source.start([...])          # spawns the background task; one call only
    → await source.add_ticker("TSLA")    # idempotent
    → await source.remove_ticker("...")  # idempotent
    → await source.stop()                # idempotent; safe to call twice
```

Notes:

- `start()` is called exactly once. Calling twice is undefined behaviour.
- `stop()` is idempotent — used in shutdown handlers and test teardown.
- `add_ticker` / `remove_ticker` are idempotent. Adding an already‑tracked ticker is a no‑op.
- The source **does not return prices**. It pushes into the cache. Reading prices is the cache's job.

---

## 6. Factory — `create_market_data_source`

Selects the implementation at startup based on environment.

```python
def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        return MassiveDataSource(api_key=api_key, price_cache=price_cache)
    return SimulatorDataSource(price_cache=price_cache)
```

The factory returns an unstarted source. The caller is responsible for awaiting `start(tickers)`.

Selection rules:

- `MASSIVE_API_KEY` set and non‑empty → `MassiveDataSource` (real data).
- Otherwise → `SimulatorDataSource` (GBM simulation).
- There is no auto‑fallback. If the Massive API fails at runtime, the simulator is **not** swapped in — the cache simply goes stale until the API recovers. We prefer obvious staleness over silent fakery.

---

## 7. SimulatorDataSource (default)

Wraps `GBMSimulator` (see `MARKET_SIMULATOR.md`) in an asyncio loop.

Tunables:

| Param | Default | Meaning |
|-------|---------|---------|
| `update_interval` | `0.5` s | How often `step()` runs |
| `event_probability` | `0.001` | Per‑tick chance of a 2–5% shock per ticker |

On `start(tickers)`:
1. Constructs a `GBMSimulator` with those tickers.
2. **Seeds the cache immediately** with the simulator's starting prices, so SSE clients connecting in the first 500 ms get data.
3. Spawns the background asyncio task.

The task body, simplified:

```python
async def _run_loop(self) -> None:
    while True:
        try:
            prices = self._sim.step()                # dict[str, float]
            for ticker, price in prices.items():
                self._cache.update(ticker=ticker, price=price)
        except Exception:
            logger.exception("Simulator step failed")
        await asyncio.sleep(self._interval)
```

Errors in `step()` are caught — a single bad tick must not kill the whole simulator.

---

## 8. MassiveDataSource

Polls Massive's snapshot endpoint for all watched tickers.

Tunables:

| Param | Default | Meaning |
|-------|---------|---------|
| `poll_interval` | `15.0` s | Suitable for the free tier (5 req/min) |

On `start(tickers)`:
1. Constructs the synchronous `RESTClient`.
2. Does an **immediate first poll** before scheduling the loop, so SSE has data right away.
3. Spawns the background asyncio task.

The poll body, simplified:

```python
async def _poll_once(self) -> None:
    if not self._tickers or not self._client:
        return
    try:
        snapshots = await asyncio.to_thread(
            self._client.get_snapshot_all,
            market_type=SnapshotMarketType.STOCKS,
            tickers=self._tickers,
        )
        for snap in snapshots:
            self._cache.update(
                ticker=snap.ticker,
                price=snap.last_trade.price,
                timestamp=snap.last_trade.timestamp / 1000.0,
            )
    except Exception as exc:
        logger.error("Massive poll failed: %s", exc)
```

`asyncio.to_thread` keeps the event loop unblocked while the synchronous SDK call is in flight.

See `MASSIVE_API.md` for the API surface used here.

---

## 9. SSE Streaming (the consumer side)

`stream.py` exposes a FastAPI router factory. The endpoint reads from the cache and pushes Server‑Sent Events to the browser.

```python
def create_stream_router(price_cache: PriceCache) -> APIRouter: ...
# GET /api/stream/prices  → text/event-stream
```

Mechanics:

- Subscribes to the cache via `price_cache.version` polling at 500 ms.
- Only emits an event when `version` actually changes (no idle traffic).
- Sends `retry: 1000\n\n` so the browser's `EventSource` reconnects automatically on a drop.
- Uses `request.is_disconnected()` to break the loop cleanly when the client goes away.
- Payload shape: `data: {"AAPL": {ticker, price, previous_price, timestamp, change, change_percent, direction}, ...}\n\n`.

This decoupling — cache as the single point of truth — means we can have many concurrent SSE clients without re‑hitting the data source.

---

## 10. End‑to‑End Lifecycle

Typical FastAPI app startup:

```python
from app.market import (
    PriceCache, create_market_data_source, create_stream_router,
)

DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
                   "NVDA", "META", "JPM", "V", "NFLX"]

cache = PriceCache()
source = create_market_data_source(cache)

@app.on_event("startup")
async def _startup() -> None:
    await source.start(DEFAULT_TICKERS)

@app.on_event("shutdown")
async def _shutdown() -> None:
    await source.stop()

app.include_router(create_stream_router(cache))
```

Watchlist mutation (e.g. from `POST /api/watchlist`):

```python
await source.add_ticker(ticker)       # next tick will include it
# or
await source.remove_ticker(ticker)    # also clears from cache
```

Reading prices for trade execution:

```python
update = cache.get("AAPL")
if update is None:
    raise HTTPException(503, "Price not yet available")
fill_price = update.price
```

---

## 11. Testing Strategy

The interface is the seam we test against. Tests live in `backend/tests/market/`:

| File | What it covers |
|------|----------------|
| `test_models.py` | `PriceUpdate` immutability, properties, serialization |
| `test_cache.py` | First‑write semantics, version counter, thread safety, removal |
| `test_simulator.py` | GBM math, correlation matrix, ticker add/remove, event shocks |
| `test_simulator_source.py` | Lifecycle: start → tick → cache populated → stop |
| `test_massive.py` | Poller behaviour with the SDK mocked at the import boundary |
| `test_factory.py` | Env‑driven selection between simulator and Massive |

The contract — that both sources implement the ABC and write `PriceUpdate`s into the cache — is what consumers depend on. As long as that holds, the simulator is a faithful stand‑in for the real API in tests, demos, and CI.

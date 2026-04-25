# Market Data Backend — Code Review

**Date:** 2026-04-26
**Reviewer:** Claude Opus 4.7
**Scope:** `backend/app/market/` (8 source files) and `backend/tests/market/` (6 test files)
**Spec:** `planning/MARKET_DATA_DESIGN.md`, `MARKET_INTERFACE.md`, `MARKET_SIMULATOR.md`, `MASSIVE_API.md`, `PLAN.md`

**Verdict:** Production-ready for its intended use (capstone demo). All tests pass, lint is clean, coverage is high, and the implementation faithfully follows the design contract. A handful of minor issues are documented below — none block shipping; one (the SSE router factory) is worth addressing before the broader API layer lands on top of it.

---

## 1. Test, Lint, Coverage

### Tests — 73 passed / 73 collected (2.93 s)

```
tests/market/test_cache.py          13 passed
tests/market/test_factory.py         7 passed
tests/market/test_massive.py        13 passed
tests/market/test_models.py         11 passed
tests/market/test_simulator.py      19 passed
tests/market/test_simulator_source.py 10 passed
```

Run with `cd backend && uv run --extra dev pytest -v`.

### Lint — clean

```
$ uv run --extra dev ruff check app/ tests/
All checks passed!
```

### Coverage — 91 % overall

| Module | Stmts | Miss | Cover | Notes |
|---|---|---|---|---|
| `app/__init__.py` | 0 | 0 | 100 % | |
| `app/market/__init__.py` | 6 | 0 | 100 % | |
| `app/market/models.py` | 26 | 0 | 100 % | |
| `app/market/cache.py` | 39 | 0 | 100 % | |
| `app/market/interface.py` | 13 | 0 | 100 % | |
| `app/market/seed_prices.py` | 8 | 0 | 100 % | |
| `app/market/factory.py` | 15 | 0 | 100 % | |
| `app/market/simulator.py` | 139 | 3 | 98 % | L149 (`_add_ticker_internal` duplicate guard); L268-269 (`_run_loop` exception log) |
| `app/market/massive_client.py` | 67 | 4 | 94 % | L85-87 (`_poll_loop` body); L125 (`_fetch_snapshots` real call) — both unreachable without a live API |
| `app/market/stream.py` | 36 | 24 | 33 % | SSE generator body — never exercised; see Finding 2.1 |
| **TOTAL** | **349** | **31** | **91 %** | |

The previous review (archived 2026-02-10) was at 84 % overall with the same `stream.py` gap; the gain comes from the Massive client now being properly testable (was 56 %, now 94 %). The only remaining hot spot is `stream.py`.

---

## 2. Findings

Severity legend: **P0** = blocks shipping. **P1** = fix before building on top of this. **P2** = nice-to-have.

### 2.1 [P1] `stream.py`: module-level router defeats the factory pattern

The `create_stream_router` factory returns a router that was created at module load time, not inside the function:

```python
# app/market/stream.py
router = APIRouter(prefix="/api/stream", tags=["streaming"])  # module-level

def create_stream_router(price_cache: PriceCache) -> APIRouter:
    @router.get("/prices")                                    # registers on the module router
    async def stream_prices(request: Request) -> StreamingResponse:
        ...
    return router
```

**Why this matters.** The function is named `create_stream_router` and the design doc describes "factory pattern lets us inject the cache without globals." But a second call would (a) register `/prices` on the same router again — FastAPI happily appends duplicate routes — and (b) the inner closure captures the most-recent `price_cache`, so older routers all alias the latest cache. In tests or any future multi-instance scenario this fails silently.

**Today's blast radius:** zero. The app calls it exactly once at startup. But the API layer that's about to be built on top of this will inevitably want to import the module and accidentally trigger registration order issues, or write a test that creates a second app instance. Cheap to fix now, painful to debug later.

**Fix.** Move the router inside the function:

```python
def create_stream_router(price_cache: PriceCache) -> APIRouter:
    router = APIRouter(prefix="/api/stream", tags=["streaming"])

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _generate_events(price_cache, request),
            media_type="text/event-stream",
            headers={...},
        )

    return router
```

### 2.2 [P2] `MassiveDataSource._poll_once`: race when removing a ticker mid-poll

Sequence:

1. `_poll_once` enters `await asyncio.to_thread(self._fetch_snapshots)` — yields to the event loop.
2. While the thread is mid-flight, another coroutine calls `await source.remove_ticker("AAPL")`. That mutates `self._tickers` and clears `cache["AAPL"]`.
3. The thread returns with snapshots that include `AAPL` (because the SDK was asked for it before the mutation, or the timing crossed inside the SDK's join).
4. `_poll_once` resumes; the for loop writes `AAPL`'s price back into the cache.
5. Subsequent polls don't ask for `AAPL` (it's no longer in `_tickers`), so the stale entry sits in the cache forever and is emitted on every SSE tick.

Symptom: a removed ticker reappears for one frame, then sticks around as a stale entry until the process restarts.

**Severity:** low (visual glitch, no data corruption, only on rapid remove timing).

**Fix.** Filter snapshots to the current ticker set inside the for loop:

```python
for snap in snapshots:
    if snap.ticker not in self._tickers:
        continue                         # was removed during the poll
    try:
        ...
        self._cache.update(...)
```

A single line, no extra locking required (this code runs on the event loop and `_tickers` is mutated only on the event loop, so the read is atomic with respect to the write).

### 2.3 [P2] Asymmetry between `SimulatorDataSource.add_ticker` and `MassiveDataSource.add_ticker`

`SimulatorDataSource.add_ticker` seeds the cache immediately:

```python
self._sim.add_ticker(ticker)
price = self._sim.get_price(ticker)
if price is not None:
    self._cache.update(ticker=ticker, price=price)
```

`MassiveDataSource.add_ticker` does not — the new ticker won't appear in the cache until the next poll, up to 15 s later on the free tier:

```python
if ticker not in self._tickers:
    self._tickers.append(ticker)
    logger.info("Massive: added ticker %s (will appear on next poll)", ticker)
```

**Why it matters.** A user adding a ticker to the watchlist sees it appear instantly in simulator mode but with a 15 s lag in Massive mode. The frontend needs a "loading" affordance for the Massive case anyway, but the asymmetry is worth flagging — it makes the two implementations subtly non-substitutable.

**Options.**
- **Accept.** Documented in the log message; arguably correct (we don't know the price yet).
- **Trigger an immediate poll on add.** `await self._poll_once()` after the append. One extra API call per add, but means the cache gets seeded in roughly one round-trip. On the free tier this consumes one of five minute-budget calls per add.
- **Optimistic placeholder.** Insert a `PriceUpdate` with `price=0.0, direction="flat"` so the SSE consumer can render a "—" cell until the real price arrives. This bleeds into UX territory and probably isn't the right fix here.

I'd lean toward **trigger an immediate poll on add** if the watchlist mutates infrequently (which it does — user-driven), capped to one extra poll per user action. Cheap and obvious to the operator.

### 2.4 [P2] Inconsistent ticker normalization between sources

`MassiveDataSource` normalizes:

```python
async def add_ticker(self, ticker: str) -> None:
    ticker = ticker.upper().strip()
    ...
```

`SimulatorDataSource` and `GBMSimulator` do not:

```python
def add_ticker(self, ticker: str) -> None:
    if ticker in self._prices:
        return
    self._add_ticker_internal(ticker)
    self._rebuild_cholesky()
```

If `add_ticker(" aapl ")` is called against the simulator, it stores `" aapl "` as a distinct ticker from `"AAPL"`. The factory hides this from callers, but if the API layer trusts whichever data source it gets and forgets to normalize at the route boundary, the bug surfaces only in simulator mode (the most common one — the demo).

**Fix.** Normalize at the source boundary in both implementations, OR push normalization up to the API layer and remove it from `MassiveDataSource`. The first is the smaller change:

```python
# simulator.py — SimulatorDataSource
async def add_ticker(self, ticker: str) -> None:
    ticker = ticker.upper().strip()
    if self._sim:
        self._sim.add_ticker(ticker)
        ...

async def remove_ticker(self, ticker: str) -> None:
    ticker = ticker.upper().strip()
    if self._sim:
        self._sim.remove_ticker(ticker)
    self._cache.remove(ticker)
```

(The underlying `GBMSimulator` is "trust the input" — fine, since only its async wrapper is part of the public ABC.)

### 2.5 [P2] SSE endpoint has 33 % coverage and no end-to-end test

`stream.py` is the consumer-side seam between the cache and the browser. The existing tests don't exercise it at all. The current coverage gap is honest (24 missed lines = entire generator body), but this is the module most likely to break in subtle ways:

- Headers wrong → browser misbehaves silently.
- `is_disconnected()` polling wrong → connections leak.
- Version-counter logic wrong → either spam every 500 ms or never emit.

**Fix.** Add a single FastAPI integration test that:

1. Stands up a `FastAPI()` with `create_stream_router(cache)`.
2. Uses `httpx.AsyncClient(app=app, base_url="http://test")` with `timeout=2`.
3. Hits `/api/stream/prices` as a streaming response, reads the first event, asserts shape.
4. Mutates the cache, reads the next event, asserts the new price is present.
5. Closes the client; asserts the generator's `is_disconnected` exits cleanly.

Should add ~30 statements of coverage and catch any header / format / disconnect regression.

### 2.6 [P2] Nits

- **`tests/conftest.py:7`**: the `event_loop_policy` fixture is defined but never referenced. With `asyncio_mode = "auto"` set in `pyproject.toml` it isn't needed. Remove.
- **`massive_client.py:123`**: `_fetch_snapshots` returns `list` (unparameterized). Either `list[Any]` or — better — import the SDK's snapshot type and parameterize.
- **`massive_client.py:_fetch_snapshots`**: the spec mentions `include_otc=False`. The SDK default is currently `False` so behavior is correct, but passing it explicitly future-proofs against an SDK default change.
- **`MassiveDataSource.stop()`** sets `self._client = None`; **`SimulatorDataSource.stop()`** does not null out `self._sim`. Both are fine in practice (the task is cancelled either way), but consistency reads better.
- **`test_immutability`** in `test_models.py` catches `AttributeError`. `dataclasses.FrozenInstanceError` (a subclass) is the more specific assertion.

---

## 3. Spec Conformance

Audited against `MARKET_DATA_DESIGN.md` section by section. Summary: **complete and faithful.**

| Spec section | Implementation | Status |
|---|---|---|
| `PriceUpdate` (frozen dataclass with `change`/`change_percent`/`direction`/`to_dict`) | `models.py` | ✓ Matches exactly |
| `PriceCache` (thread-safe, version counter, first-write flat, 2 dp rounding) | `cache.py` | ✓ Matches |
| `MarketDataSource` ABC (`start`/`stop`/`add_ticker`/`remove_ticker`/`get_tickers`) | `interface.py` | ✓ Matches |
| Seed prices, GBM params, correlation groups, `TSLA` independence | `seed_prices.py` | ✓ Matches |
| `GBMSimulator` math (`exp((mu - 0.5σ²)dt + σ√dt·Z)`, Cholesky correlation, shock model) | `simulator.py` | ✓ Matches; `dt = 8.48e-8` |
| `SimulatorDataSource` (immediate cache seeding, error-resilient run loop, idempotent stop) | `simulator.py` | ✓ Matches |
| `MassiveDataSource` (single `get_snapshot_all` per poll, ms→s timestamp, `asyncio.to_thread`, error-swallowing) | `massive_client.py` | ✓ Matches |
| Factory env-driven selection (`MASSIVE_API_KEY` set → Massive, else Simulator) | `factory.py` | ✓ Matches |
| SSE router (`/api/stream/prices`, version-based change detection, `retry: 1000`, disconnect handling) | `stream.py` | ✓ Behavior matches; structure has Finding 2.1 |

No spec items are missing.

---

## 4. Strengths

- **Clean strategy pattern.** Two implementations, one ABC, one cache. The factory is a four-line branch on an env var. Downstream code is fully source-agnostic.
- **Sync/async boundary handled correctly.** The Massive SDK is synchronous; the implementation wraps it in `asyncio.to_thread` and pairs it with a `threading.Lock` on the cache. The lock is microseconds-held, the cache is small, no contention is plausible.
- **Math is right.** The GBM step matches the closed-form solution. Cholesky decomposition produces the intended sector correlation. The corner case (`n ≤ 1` → `cholesky = None`) is handled. The `TSLA`-as-its-own-thing rule is implemented exactly as specified.
- **Failure mode is honest.** The Massive poller swallows-and-logs on errors (401, 429, 5xx, network). The cache simply goes stale, which is visible to operators (no SSE updates) rather than silently faked. `CancelledError` correctly propagates because it's a `BaseException`, not an `Exception`.
- **Tests are well-targeted.** Models, cache, and the simulator math have full unit coverage. The Massive client is mocked at the right boundary (the bound method `_fetch_snapshots`, not `RESTClient` itself) — that's the choice that fixed the previous review's 5 failures and lifted coverage from 56 % to 94 %. The integration tests for `SimulatorDataSource` exercise real timing without slowing the suite down (intervals scaled to 50–100 ms).
- **Public API is small and well-named.** `from app.market import PriceUpdate, PriceCache, MarketDataSource, create_market_data_source, create_stream_router` is everything a downstream module needs. No leaking internals.
- **Performance headroom.** `step()` at the default tick (500 ms, 10 tickers) takes microseconds; the Cholesky multiply is `n² = 100` flops per tick. Even at 50 tickers it's well below 1 ms. The cache lock is held only during the dictionary write. No bottlenecks visible.

---

## 5. Recommendations

In priority order:

1. **Fix the SSE router factory** (Finding 2.1). One-paragraph change, prevents a future debugging session.
2. **Filter Massive snapshots by current ticker set** (Finding 2.2). One line; closes the remove-during-poll race.
3. **Normalize tickers in `SimulatorDataSource.add_ticker` / `remove_ticker`** (Finding 2.4). Two `.upper().strip()` calls.
4. **Decide on Massive's add-ticker latency** (Finding 2.3). Either accept the 15 s lag and document it for the frontend, or trigger an immediate `_poll_once()` after `_tickers.append`.
5. **Add a single SSE integration test** (Finding 2.5). Brings coverage to ~96 %, catches header/format/disconnect regressions.
6. **Tidy nits** (Finding 2.6). Remove unused fixture, parameterize `_fetch_snapshots` return type, pass `include_otc=False` explicitly, tighten the immutability assertion.

The first three together are roughly twenty lines of code and a handful of test additions. They can ship as a single small PR titled "market data: tighten factory, race, and normalization."

---

## 6. Conclusion

The market data subsystem is implemented to the spec, well-tested (73 / 73 passing, 91 % coverage, lint clean), and architecturally sound. Nothing here blocks the next phase of the build. The only finding I'd flag as worth doing before more code lands on top of this is the SSE router factory (2.1) — everything else is small enough to bundle into a routine cleanup PR.

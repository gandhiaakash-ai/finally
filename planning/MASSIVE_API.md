# Massive API Reference (formerly Polygon.io)

Reference for the Massive Python client (`massive`, formerly `polygon-api-client`) as used by FinAlly to fetch real‑time and end‑of‑day stock prices.

This document is the source of truth for which Massive endpoints we call, the request shape, and the response fields we extract. The actual client lives in `backend/app/market/massive_client.py`.

---

## 1. Quick Facts

| Item | Value |
|------|-------|
| Package | `massive` (PyPI) |
| Install | `uv add massive` |
| Min Python | 3.9+ (FinAlly targets 3.12) |
| Base URL | `https://api.massive.com` (legacy `https://api.polygon.io` still works) |
| Auth | API key via `MASSIVE_API_KEY` env var, or `RESTClient(api_key=...)` |
| Auth header | `Authorization: Bearer <KEY>` (handled by client) |
| SDK style | Synchronous. We wrap calls in `asyncio.to_thread(...)` so they don't block the event loop. |

### Rate limits

| Tier | Limit | Recommended FinAlly poll interval |
|------|-------|------------------------------------|
| Free | 5 requests / minute | 15 s |
| Starter | 100 / minute | 5 s |
| Developer+ | Unlimited (soft cap ~100 req/s) | 2 s |

Because we batch all watched tickers into a single snapshot call, one poll = one request. With the default 10‑ticker watchlist the free tier is sufficient.

---

## 2. Client Initialization

```python
from massive import RESTClient

# Reads MASSIVE_API_KEY from the environment automatically
client = RESTClient()

# Or pass explicitly (FinAlly does this so behavior is independent of process env)
client = RESTClient(api_key="your_key_here")
```

The client manages connection pooling internally. Construct it once at startup, reuse for all calls, and let it be garbage‑collected on shutdown.

---

## 3. Endpoints Used by FinAlly

We use a small, deliberately narrow subset of the API.

### 3.1 Snapshot — All Tickers (the primary endpoint)

Returns the latest snapshot for an arbitrary set of tickers in **a single call**. This is the workhorse of our live‑price loop.

REST: `GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,GOOGL,MSFT`

```python
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

client = RESTClient()

snapshots = client.get_snapshot_all(
    market_type=SnapshotMarketType.STOCKS,
    tickers=["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"],
    include_otc=False,
)

for snap in snapshots:
    print(f"{snap.ticker}: ${snap.last_trade.price:.2f}  "
          f"(day close ${snap.day.close:.2f}, "
          f"{snap.todays_change_perc:+.2f}%)")
```

Each snapshot exposes (fields most relevant to FinAlly are bolded):

| Path | Type | Notes |
|------|------|-------|
| **`snap.ticker`** | `str` | Ticker symbol |
| **`snap.last_trade.price`** | `float` | Most recent traded price — the value we cache |
| **`snap.last_trade.timestamp`** | `int` | Unix **milliseconds** — divide by 1000 for seconds |
| `snap.last_trade.size` | `int` | Trade size |
| `snap.last_trade.exchange` | `str` | Exchange MIC |
| `snap.last_quote.bid_price` / `bid_size` | `float` / `int` | NBBO bid |
| `snap.last_quote.ask_price` / `ask_size` | `float` / `int` | NBBO ask |
| `snap.day.open` | `float` | Today's open |
| `snap.day.high` | `float` | Today's high |
| `snap.day.low` | `float` | Today's low |
| `snap.day.close` | `float` | Today's close (during market hours, last print) |
| `snap.day.volume` | `int` | Day volume |
| `snap.day.previous_close` | `float` | Previous trading day's close |
| **`snap.todays_change_perc`** | `float` | Day change %, pre‑computed by Massive |
| `snap.todays_change` | `float` | Day change in dollars |
| `snap.prev_daily_bar.{o,h,l,c,v}` | nested | Full prior‑day bar |
| `snap.minute_volume` | nested | Per‑minute volume map |

Behaviour outside market hours: `last_trade.price` continues to reflect the last print (which may include extended hours). `day.*` fields are scoped to the current session and reset at the next open.

### 3.2 Snapshot — Single Ticker

Used when we want a richer detail view for one ticker (e.g. when the user clicks a row in the watchlist).

```python
snap = client.get_snapshot_ticker(
    market_type=SnapshotMarketType.STOCKS,
    ticker="AAPL",
)

print(f"Price:  ${snap.last_trade.price:.2f}")
print(f"Bid/Ask: ${snap.last_quote.bid_price:.2f} / ${snap.last_quote.ask_price:.2f}")
print(f"Day range: ${snap.day.low:.2f} – ${snap.day.high:.2f}")
```

Functionally equivalent to `get_snapshot_all(tickers=["AAPL"])[0]` but cheaper if you only want one ticker.

### 3.3 Previous Close (end‑of‑day)

Returns yesterday's OHLCV for a single ticker. Useful for seeding charts, day‑change calculations when a snapshot is unavailable, or "what was the last close" lookups.

REST: `GET /v2/aggs/ticker/{ticker}/prev`

```python
prev = client.get_previous_close_agg(ticker="AAPL", adjusted=True)
print(f"AAPL prev close: ${prev.close:.2f}  Volume: {prev.volume:,}")
print(f"OHLC: O={prev.open} H={prev.high} L={prev.low} C={prev.close}")
```

`adjusted=True` applies splits/dividend adjustments. We default to `True`.

### 3.4 Aggregates (historical bars)

OHLCV bars over a date range — used only when we want to plot historical context, not for live polling.

REST: `GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}`

```python
bars = list(client.list_aggs(
    ticker="AAPL",
    multiplier=1,
    timespan="day",          # second | minute | hour | day | week | month | quarter | year
    from_="2024-01-01",
    to="2024-12-31",
    adjusted=True,
    sort="asc",
    limit=50000,
))

for b in bars[:5]:
    print(f"{b.timestamp}  O={b.open} H={b.high} L={b.low} C={b.close} V={b.volume}")
```

`list_aggs` is a generator that auto‑paginates. Cap `limit` per page; the SDK loops for you.

### 3.5 Last Trade / Last Quote (single, lightweight)

Mostly redundant with the snapshot endpoints, but available if you only need the current trade or NBBO and want the smallest possible response.

```python
trade = client.get_last_trade(ticker="AAPL")
print(f"{trade.price} x {trade.size} @ {trade.sip_timestamp}")

quote = client.get_last_quote(ticker="AAPL")
print(f"Bid {quote.bid} x {quote.bid_size}  /  Ask {quote.ask} x {quote.ask_size}")
```

---

## 4. How FinAlly Uses the API

A single background poller calls `get_snapshot_all` on a fixed interval and writes the results to the shared in‑memory `PriceCache`. Everything downstream — SSE streaming, portfolio valuation, trade execution — reads from the cache.

The full implementation lives in `backend/app/market/massive_client.py`; the relevant inner loop:

```python
async def _poll_once(self) -> None:
    if not self._tickers or not self._client:
        return
    try:
        # Massive's RESTClient is synchronous; run in a thread so we don't
        # block the asyncio loop.
        snapshots = await asyncio.to_thread(
            self._client.get_snapshot_all,
            market_type=SnapshotMarketType.STOCKS,
            tickers=self._tickers,
        )
        for snap in snapshots:
            self._cache.update(
                ticker=snap.ticker,
                price=snap.last_trade.price,
                timestamp=snap.last_trade.timestamp / 1000.0,  # ms → s
            )
    except Exception as exc:
        logger.error("Massive poll failed: %s", exc)
        # Don't re-raise — let the loop retry on the next interval.
```

Key design points:

- **One snapshot call per poll**, regardless of watchlist size. This is what makes the free tier viable.
- **`asyncio.to_thread`** — the SDK is sync, so we keep the event loop unblocked.
- **Errors swallowed and logged** — a transient 5xx or rate‑limit response should not kill the poller. The next tick retries.
- **Timestamps normalized to Unix seconds** at the boundary, because the rest of the system speaks seconds (matching `time.time()`).

---

## 5. Error Modes

| HTTP | Meaning | What FinAlly does |
|------|---------|-------------------|
| 401 | Bad / missing API key | Logs error; loop continues. Operator should fix `MASSIVE_API_KEY`. |
| 403 | Plan does not include endpoint | Same — surface in logs, keep running on whatever still works. |
| 429 | Rate limit exceeded | Logs error; next poll happens after `poll_interval`. Increase the interval if frequent. |
| 5xx | Massive server error | The SDK retries up to 3× internally with backoff; if it still fails we log and wait for the next tick. |
| Network / DNS | Connection error | Same as 5xx — log and retry. |

We deliberately do not surface API failures to the frontend. The price cache simply goes stale, and stale prices are clearly visible (the SSE stream stops emitting changes). When the API recovers, the cache catches up automatically.

---

## 6. Notes & Gotchas

- The `tickers=` parameter on `get_snapshot_all` is the magic that lets us hit one endpoint per poll. Without it the call returns *all* US equities (~10k rows), which is wasteful and may exhaust pagination on the free tier.
- Some plans return `last_trade.price == 0` for thinly traded symbols outside market hours. Filter or fall back to `day.close` if you observe this.
- `snap.todays_change_perc` is pre‑computed and authoritative for day P&L — prefer it over reconstructing from `last_trade.price - day.previous_close`.
- The `massive` package is a drop‑in rename of the older `polygon-api-client`. If you find an example using `from polygon import RESTClient`, the API calls are identical — only the import changes.
- The free tier serves prices on a **15‑minute delay**. Real‑time access requires a paid plan. The simulator is a better demo experience than 15‑min‑delayed real data, which is why simulator‑by‑default is the right call.

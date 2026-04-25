# Market Simulator Design

How FinAlly fakes a live stock market when no real data feed is configured.

The simulator is the default data source and the one most users (including students, testers, and CI) actually run against. It produces a realistic, never‑boring price stream without an external API. Implementation lives in `backend/app/market/simulator.py` and `backend/app/market/seed_prices.py`.

---

## 1. What "Realistic" Means Here

We're not trying to forecast or backtest — we're trying to make a trading dashboard *feel alive* and *behave plausibly*. That means:

- Prices change in small steps every ~500 ms, not in occasional big jumps.
- Prices can drift up or down over time, but with a slight positive bias (markets tend to rise).
- Volatility differs by ticker — TSLA wiggles more than JPM.
- Tickers in the same sector move together. When tech is up, most tech is up.
- Occasional "news shocks" — a few % move in seconds — keep the screen interesting.
- Prices never go negative.

These properties together are exactly what **Geometric Brownian Motion (GBM)** gives you, plus a **correlation matrix** for sector co‑movement and a **Bernoulli shock** for drama. That's the whole model.

---

## 2. The GBM Step

At each tick, every ticker's price updates as:

```
S(t + dt) = S(t) * exp((mu - 0.5 * sigma^2) * dt + sigma * sqrt(dt) * Z)
```

| Symbol | Meaning | Typical value |
|--------|---------|----------------|
| `S(t)` | Current price | seeded from `SEED_PRICES` |
| `mu`   | Annualized drift (expected return) | 0.03 – 0.08 |
| `sigma`| Annualized volatility | 0.17 – 0.50 |
| `dt`   | Time step as a fraction of a trading year | `~8.5e-8` |
| `Z`    | Standard normal draw, correlated across tickers | from N(0,1) via Cholesky |

### Why `dt ≈ 8.5e-8`

We tick every 500 ms. A trading year is 252 days × 6.5 hours × 3600 s = 5,896,800 seconds. So:

```
dt = 0.5 / 5_896_800 ≈ 8.48e-8
```

This makes per‑tick moves sub‑cent. Daily volatility (~`sigma / sqrt(252)`) emerges naturally from accumulating thousands of these tiny steps. Stretch the simulator over a session and you'll see roughly the right intraday range without ever tuning anything other than `sigma`.

### Why GBM and not, say, a random walk

- GBM is *multiplicative* (`exp(...)`), so prices stay positive without any clipping.
- It produces lognormal returns — the actual statistical shape real prices follow.
- The math is closed‑form per step; one `np.exp` and one Cholesky multiply per tick is fast.

---

## 3. Correlated Moves

Stocks don't move independently — that's why "the market is up" is even a meaningful sentence. The simulator captures this with a correlation matrix and a **Cholesky decomposition**.

Given a correlation matrix `C` (positive semi‑definite by construction), compute `L = cholesky(C)`. Then:

```
Z_correlated = L @ Z_independent
```

where `Z_independent` is a vector of independent standard normals. The result is a vector of correlated normals with the desired correlation structure. We feed that into the GBM step.

### Correlation groups (from `seed_prices.py`)

```python
CORRELATION_GROUPS = {
    "tech":    {"AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "NFLX"},
    "finance": {"JPM", "V"},
}

INTRA_TECH_CORR    = 0.6   # within tech
INTRA_FINANCE_CORR = 0.5   # within finance
CROSS_GROUP_CORR   = 0.3   # tech ↔ finance, or with unknown tickers
TSLA_CORR          = 0.3   # TSLA correlates loosely with everyone
```

`TSLA` is technically in the tech set but behaves on its own — its correlation with everything is forced down to 0.3. That's a deliberate choice: TSLA visibly diverging from the pack adds visual variety to the dashboard.

The matrix is rebuilt only when the watchlist changes (via `add_ticker` / `remove_ticker`), which is rare. Construction is O(n²), Cholesky is O(n³), but `n < 50` in practice — both are negligible.

---

## 4. Random Shocks ("News")

Plain GBM is realistic but visually monotonous. To make the dashboard feel alive we add a Bernoulli shock at every tick, per ticker:

```python
if random.random() < self._event_prob:        # default 0.001
    shock_magnitude = random.uniform(0.02, 0.05)   # 2% – 5%
    shock_sign      = random.choice([-1, 1])
    self._prices[ticker] *= 1 + shock_magnitude * shock_sign
```

With `event_prob = 0.001` and 10 tickers ticking every 500 ms, expect a shock somewhere on the screen roughly every 50 seconds. Often enough to catch the eye, rare enough not to feel like a casino.

The default is tuned for "lively". Drop it to `0.0001` for a calmer market, raise it to `0.005` if you want a chaotic demo.

---

## 5. Per‑Ticker Parameters

Each known ticker has its own `mu` and `sigma`, chosen to roughly mirror real‑world behaviour. From `seed_prices.py`:

| Ticker | sigma | mu   | Personality                 |
|--------|-------|------|-----------------------------|
| AAPL   | 0.22  | 0.05 | Steady big‑cap              |
| GOOGL  | 0.25  | 0.05 | Steady big‑cap              |
| MSFT   | 0.20  | 0.05 | Lowest‑vol tech             |
| AMZN   | 0.28  | 0.05 | Slightly jumpier            |
| **TSLA** | 0.50 | 0.03 | High vol, modest drift      |
| **NVDA** | 0.40 | 0.08 | High vol *and* strong drift |
| META   | 0.30  | 0.05 |                             |
| **JPM** | 0.18 | 0.04 | Calm bank                   |
| **V**   | 0.17 | 0.04 | Calm payments               |
| NFLX   | 0.35  | 0.05 | Mid‑vol media               |

Tickers added at runtime that aren't in this table fall back to:

```python
DEFAULT_PARAMS = {"sigma": 0.25, "mu": 0.05}
SEED_PRICE     = random.uniform(50.0, 300.0)   # if not in SEED_PRICES
```

`SEED_PRICES` itself is just realistic starting points (AAPL ≈ $190, NVDA ≈ $800, etc.).

---

## 6. The `GBMSimulator` Class

Pure model — no asyncio, no I/O, no cache awareness. The async wrapper lives separately in `SimulatorDataSource` (see `MARKET_INTERFACE.md`).

```python
class GBMSimulator:
    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600           # 5_896_800
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR           # ~8.48e-8

    def __init__(
        self,
        tickers: list[str],
        dt: float = DEFAULT_DT,
        event_probability: float = 0.001,
    ) -> None: ...

    # --- Public API ---

    def step(self) -> dict[str, float]:
        """Advance all tickers by one time step. Returns {ticker: price}."""

    def add_ticker(self, ticker: str) -> None:
        """Add a ticker. Rebuilds the Cholesky decomposition."""

    def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker. Rebuilds the Cholesky decomposition."""

    def get_price(self, ticker: str) -> float | None: ...
    def get_tickers(self) -> list[str]: ...
```

### Hot path: `step()`

This runs every 500 ms. The whole hot loop is roughly:

```python
def step(self) -> dict[str, float]:
    n = len(self._tickers)
    if n == 0:
        return {}

    # 1. Independent normals
    z_independent = np.random.standard_normal(n)

    # 2. Correlate via Cholesky (None when n <= 1)
    z_correlated = (
        self._cholesky @ z_independent
        if self._cholesky is not None
        else z_independent
    )

    # 3. GBM step + optional shock per ticker
    result: dict[str, float] = {}
    for i, ticker in enumerate(self._tickers):
        params = self._params[ticker]
        mu, sigma = params["mu"], params["sigma"]

        drift     = (mu - 0.5 * sigma**2) * self._dt
        diffusion = sigma * math.sqrt(self._dt) * z_correlated[i]
        self._prices[ticker] *= math.exp(drift + diffusion)

        if random.random() < self._event_prob:
            mag  = random.uniform(0.02, 0.05)
            sign = random.choice([-1, 1])
            self._prices[ticker] *= 1 + mag * sign

        result[ticker] = round(self._prices[ticker], 2)

    return result
```

NumPy handles the Cholesky multiply in vectorised C; the per‑ticker loop is then just two scalar multiplies and an `exp`. Even at 50 tickers, `step()` is well under a millisecond.

### Internal state

- `_tickers: list[str]` — order matters; matches Cholesky matrix rows.
- `_prices: dict[str, float]` — current full‑precision price per ticker.
- `_params: dict[str, dict[str, float]]` — `{ticker: {"mu": ..., "sigma": ...}}`.
- `_cholesky: np.ndarray | None` — None when `n <= 1` (no correlation possible).

### `_rebuild_cholesky()`

Called when the ticker set changes. Builds a symmetric correlation matrix using `_pairwise_correlation(t1, t2)`, then runs `np.linalg.cholesky`. Because the correlation rules above always yield a positive‑semi‑definite matrix, Cholesky never fails.

---

## 7. File Structure

```
backend/app/market/
├── simulator.py        # GBMSimulator + SimulatorDataSource
└── seed_prices.py      # SEED_PRICES, TICKER_PARAMS, DEFAULT_PARAMS,
                        # CORRELATION_GROUPS, INTRA_*_CORR, etc.
```

`seed_prices.py` is intentionally just constants. Keeping it data‑only means tweaks (a new ticker's vol, a different sector grouping) are one‑line changes that don't touch model code.

`SimulatorDataSource` (the async wrapper that conforms to `MarketDataSource`) lives at the bottom of `simulator.py`. It's documented in `MARKET_INTERFACE.md` since it's part of the interface surface, not the model.

---

## 8. Behavioural Properties to Rely On

These hold by construction — useful when writing tests or reasoning about the demo:

- **Prices stay positive.** GBM is multiplicative through `exp(...)`, which is always positive.
- **Mean‑reverting in the short term, drifting in the long term.** Per‑tick changes are dominated by the diffusion term; over thousands of ticks, drift wins.
- **Correlation is symmetric and bounded.** All off‑diagonal entries are in [0.3, 0.6]. Cholesky always succeeds.
- **First tick after `add_ticker`** is uncorrelated with prior history (the Cholesky matrix is rebuilt fresh).
- **Removing a ticker** removes its row/column and re‑decomposes — other tickers are unaffected.
- **Two `GBMSimulator`s with the same seed produce the same path.** Tests that need determinism can `random.seed(...)` and `np.random.seed(...)`.

---

## 9. What the Simulator Does Not Try to Do

- No order book, bid/ask, or microstructure. The price is the price.
- No after‑hours / pre‑market sessions — the simulator runs continuously.
- No fundamentals — earnings, splits, dividends don't exist.
- No dependence on real macro state. AAPL doesn't know what the S&P did.
- No regime changes (bull → bear). Drift is constant per ticker for the session.

This is deliberate. Anything more would add complexity without making the demo more compelling. If we ever want richer behaviour the model can be extended in `simulator.py` without touching the interface or the cache.

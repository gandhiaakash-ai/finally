import { APIRequestContext, expect } from "@playwright/test";

/**
 * REST helpers + per-test cleanup.
 *
 * Shapes confirmed with backend-engineer:
 *  - GET /api/portfolio → { cash_balance, positions: [{ticker, quantity, avg_cost, current_price, market_value, unrealized_pl, unrealized_pl_percent}], positions_value, total_value, total_cost_basis, total_unrealized_pl }
 *  - GET /api/watchlist → { tickers: [{ ticker, price: PriceUpdate|null }] }
 *  - POST /api/portfolio/trade {ticker, side, quantity} → 200 { trade, portfolio } | 400 | 422
 *  - POST /api/watchlist {ticker} → 200 { ticker, added: bool, tickers: string[] } (idempotent)
 *  - DELETE /api/watchlist/{ticker} → 200 { ticker, removed: true, tickers: string[] } | 404
 */
export const DEFAULT_WATCHLIST = [
  "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
  "NVDA", "META", "JPM", "V", "NFLX",
];

export async function getPortfolio(api: APIRequestContext) {
  const res = await api.get("/api/portfolio");
  expect(res.ok(), `GET /api/portfolio failed: ${res.status()}`).toBeTruthy();
  return res.json();
}

export async function getWatchlist(api: APIRequestContext): Promise<{
  tickers: { ticker: string; price: any }[];
}> {
  const res = await api.get("/api/watchlist");
  expect(res.ok(), `GET /api/watchlist failed: ${res.status()}`).toBeTruthy();
  return res.json();
}

export async function trade(
  api: APIRequestContext,
  body: { ticker: string; quantity: number; side: "buy" | "sell" },
) {
  const res = await api.post("/api/portfolio/trade", { data: body });
  expect(res.ok(), `POST /api/portfolio/trade failed: ${res.status()} ${await res.text()}`).toBeTruthy();
  return res.json();
}

export async function addWatchlist(api: APIRequestContext, ticker: string) {
  // Idempotent on the backend — always 200 even for duplicates.
  const res = await api.post("/api/watchlist", { data: { ticker } });
  expect(res.ok(), `POST /api/watchlist failed: ${res.status()} ${await res.text()}`).toBeTruthy();
}

export async function removeWatchlist(api: APIRequestContext, ticker: string) {
  const res = await api.delete(`/api/watchlist/${ticker}`);
  expect(res.ok() || res.status() === 404, `DELETE /api/watchlist failed: ${res.status()}`).toBeTruthy();
}

/**
 * Cleanup so each test starts from a known watchlist + zero positions.
 * Cash will not be exactly $10k after round-trip trading — tests that
 * care about absolute cash should measure deltas.
 */
export async function resetState(api: APIRequestContext) {
  const portfolio = await getPortfolio(api);
  for (const pos of portfolio.positions ?? []) {
    if ((pos.quantity ?? 0) > 0) {
      await trade(api, { ticker: pos.ticker, side: "sell", quantity: pos.quantity });
    }
  }
  const watchlist = await getWatchlist(api);
  const tickers = watchlist.tickers.map((entry) => entry.ticker);
  for (const ticker of tickers) {
    if (!DEFAULT_WATCHLIST.includes(ticker)) {
      await removeWatchlist(api, ticker);
    }
  }
  for (const ticker of DEFAULT_WATCHLIST) {
    if (!tickers.includes(ticker)) {
      await addWatchlist(api, ticker);
    }
  }
}

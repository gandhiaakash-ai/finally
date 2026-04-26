"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

/** Default tickers (per PLAN.md §7) — used as a fallback before backend responds. */
const DEFAULT_TICKERS = [
  "AAPL",
  "GOOGL",
  "MSFT",
  "AMZN",
  "TSLA",
  "NVDA",
  "META",
  "JPM",
  "V",
  "NFLX",
];

/**
 * Watchlist state synced with the backend. Returns the list of tickers plus
 * mutation helpers. Live *prices* should come from the SSE hook — this hook
 * cares only about which tickers to show.
 */
export function useWatchlist() {
  const [tickers, setTickers] = useState<string[]>(DEFAULT_TICKERS);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getWatchlist()
      .then((res) => {
        if (cancelled) return;
        setTickers(res.tickers.map((entry) => entry.ticker));
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load");
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const add = useCallback(async (ticker: string) => {
    const res = await api.addWatchlist(ticker);
    setTickers(res.tickers);
  }, []);

  const remove = useCallback(async (ticker: string) => {
    const res = await api.removeWatchlist(ticker);
    setTickers(res.tickers);
  }, []);

  return { tickers, add, remove, error, loaded };
}

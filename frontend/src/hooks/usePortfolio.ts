"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { PortfolioSummary, PortfolioSnapshot } from "@/types/api";

const POLL_INTERVAL_MS = 4000;

/**
 * Polls /api/portfolio every few seconds and exposes the latest summary
 * along with a `refresh()` callback for trade-confirmation flows.
 */
export function usePortfolio() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await api.getPortfolio();
      setSummary(next);
      setError(null);
      return next;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load";
      setError(msg);
      throw err;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const next = await api.getPortfolio();
        if (!cancelled) {
          setSummary(next);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load");
        }
      }
    };
    void tick();
    const id = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return { summary, refresh, error };
}

const HISTORY_INTERVAL_MS = 8000;

/** Polls /api/portfolio/history for the P&L line chart. */
export function usePortfolioHistory() {
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await api.getPortfolioHistory();
        if (!cancelled) {
          setSnapshots(res.snapshots);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load");
        }
      }
    };
    void tick();
    const id = setInterval(tick, HISTORY_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return { snapshots, error };
}

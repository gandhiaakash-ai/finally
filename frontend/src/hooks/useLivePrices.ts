"use client";

import { useEffect, useRef, useState } from "react";
import type { PriceUpdate } from "@/types/api";

export type ConnectionStatus = "connected" | "reconnecting" | "disconnected";

/** Maximum sparkline points kept per ticker (newest at end). */
const HISTORY_LIMIT = 240;

/**
 * Live price stream from /api/stream/prices.
 *
 * Returns a snapshot of latest prices, per-ticker history accumulated since
 * page load, and a connection-status indicator. EventSource handles
 * reconnection automatically — we mirror its state in `status`.
 *
 * The backend pushes a JSON payload of all tracked tickers on each tick:
 *   { "AAPL": { ticker, price, previous_price, timestamp, ... }, ... }
 */
export function useLivePrices() {
  const [prices, setPrices] = useState<Record<string, PriceUpdate>>({});
  const [history, setHistory] = useState<Record<string, number[]>>({});
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");

  // We use a ref so multiple updates within the same tick don't drop history.
  const historyRef = useRef<Record<string, number[]>>({});

  useEffect(() => {
    let es: EventSource | null = null;
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      setStatus((prev) => (prev === "connected" ? "reconnecting" : prev));
      es = new EventSource("/api/stream/prices");

      es.onopen = () => {
        if (cancelled) return;
        setStatus("connected");
      };

      es.onmessage = (event) => {
        if (cancelled || !event.data) return;
        try {
          const payload = JSON.parse(event.data) as Record<string, PriceUpdate>;
          setPrices((prev) => ({ ...prev, ...payload }));

          let mutated = false;
          for (const [ticker, update] of Object.entries(payload)) {
            const current = historyRef.current[ticker] ?? [];
            const last = current[current.length - 1];
            if (last !== update.price) {
              const next = [...current, update.price];
              if (next.length > HISTORY_LIMIT) {
                next.splice(0, next.length - HISTORY_LIMIT);
              }
              historyRef.current[ticker] = next;
              mutated = true;
            }
          }
          if (mutated) setHistory({ ...historyRef.current });
        } catch (err) {
          // Skip malformed payloads — keep the stream alive.
          console.warn("[useLivePrices] failed to parse SSE payload", err);
        }
      };

      es.onerror = () => {
        if (cancelled) return;
        // EventSource auto-reconnects; reflect that in our status.
        setStatus("reconnecting");
      };
    };

    connect();

    return () => {
      cancelled = true;
      es?.close();
      setStatus("disconnected");
    };
  }, []);

  return { prices, history, status };
}

"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatUsd } from "@/lib/format";
import type { TradeSide } from "@/types/api";

type Props = {
  defaultTicker?: string | null;
  onTraded?: () => void;
};

/**
 * Single-row trade bar: ticker + qty + Buy/Sell. No confirmation dialog —
 * orders fill instantly. Inline error on failure (insufficient cash etc.).
 */
export function TradeBar({ defaultTicker, onTraded }: Props) {
  const [ticker, setTicker] = useState(defaultTicker ?? "");
  const [qty, setQty] = useState("1");
  const [busy, setBusy] = useState<TradeSide | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  // Adopt the active ticker from the parent unless the user is editing.
  useEffect(() => {
    if (defaultTicker && !busy) setTicker(defaultTicker);
  }, [defaultTicker, busy]);

  const submit = async (side: TradeSide) => {
    setError(null);
    setConfirmation(null);
    const parsedTicker = ticker.trim().toUpperCase();
    const parsedQty = Number(qty);
    if (!parsedTicker) {
      setError("Ticker is required");
      return;
    }
    if (!Number.isFinite(parsedQty) || parsedQty <= 0) {
      setError("Quantity must be positive");
      return;
    }
    setBusy(side);
    try {
      const res = await api.trade({
        ticker: parsedTicker,
        side,
        quantity: parsedQty,
      });
      setConfirmation(
        `${side === "buy" ? "Bought" : "Sold"} ${parsedQty} ${parsedTicker} @ ${formatUsd(res.trade.price)}`,
      );
      onTraded?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Trade failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="panel p-3">
      <div className="flex items-center gap-2">
        <span className="text-[var(--color-text-muted)] text-xs uppercase tracking-widest mr-1">
          Trade
        </span>
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          placeholder="TICKER"
          maxLength={6}
          data-testid="trade-ticker-input"
          className="mono uppercase w-20 bg-[var(--color-bg-base)] border border-[var(--color-border-subtle)] rounded px-2 py-1.5 text-sm placeholder:normal-case placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent-blue)]"
          disabled={!!busy}
        />
        <input
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          placeholder="Qty"
          type="number"
          step="0.01"
          min="0"
          data-testid="trade-qty-input"
          className="mono w-24 bg-[var(--color-bg-base)] border border-[var(--color-border-subtle)] rounded px-2 py-1.5 text-sm focus:outline-none focus:border-[var(--color-accent-blue)]"
          disabled={!!busy}
        />
        <button
          type="button"
          onClick={() => submit("buy")}
          disabled={!!busy}
          data-testid="trade-buy-button"
          className="text-xs uppercase tracking-wider px-3 py-1.5 rounded bg-[var(--color-accent-blue)] text-white disabled:opacity-40 hover:brightness-110 transition"
        >
          {busy === "buy" ? "..." : "Buy"}
        </button>
        <button
          type="button"
          onClick={() => submit("sell")}
          disabled={!!busy}
          data-testid="trade-sell-button"
          className="text-xs uppercase tracking-wider px-3 py-1.5 rounded bg-[var(--color-accent-purple)] text-white disabled:opacity-40 hover:brightness-110 transition"
        >
          {busy === "sell" ? "..." : "Sell"}
        </button>
        <div className="flex-1" />
        {error ? (
          <span className="text-xs text-[var(--color-tick-down)]">{error}</span>
        ) : confirmation ? (
          <span className="text-xs text-[var(--color-tick-up)]">{confirmation}</span>
        ) : null}
      </div>
    </div>
  );
}

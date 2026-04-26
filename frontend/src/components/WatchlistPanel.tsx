"use client";

import { useState } from "react";
import { PriceCell } from "@/components/PriceCell";
import { Sparkline } from "@/components/Sparkline";
import { formatPercent } from "@/lib/format";
import type { PriceUpdate } from "@/types/api";

type Props = {
  tickers: string[];
  prices: Record<string, PriceUpdate>;
  history: Record<string, number[]>;
  selected: string | null;
  onSelect: (ticker: string) => void;
  onAdd: (ticker: string) => Promise<void> | void;
  onRemove: (ticker: string) => Promise<void> | void;
};

/**
 * Watchlist grid. One row per ticker:
 *   [ticker]  [sparkline]  [price]  [%-change]   [×]
 *
 * Click a row to select the ticker (drives the main chart).
 */
export function WatchlistPanel({
  tickers,
  prices,
  history,
  selected,
  onSelect,
  onAdd,
  onRemove,
}: Props) {
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const ticker = draft.trim().toUpperCase();
    if (!ticker) return;
    setBusy(true);
    setError(null);
    try {
      await onAdd(ticker);
      setDraft("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel flex flex-col h-full" data-testid="watchlist">
      <div className="panel-header">
        <span>Watchlist</span>
        <span className="text-[var(--color-text-muted)] normal-case tracking-normal">
          {tickers.length} tickers
        </span>
      </div>

      <ul className="divide-y divide-[var(--color-border-subtle)] flex-1 overflow-y-auto">
        {tickers.map((ticker) => {
          const update = prices[ticker];
          const hist = history[ticker] ?? [];
          const pct = update?.change_percent ?? 0;
          const pctClass =
            pct > 0
              ? "text-[var(--color-tick-up)]"
              : pct < 0
                ? "text-[var(--color-tick-down)]"
                : "text-[var(--color-text-muted)]";
          const isSelected = ticker === selected;

          return (
            <li
              key={ticker}
              className={`group flex items-center gap-2 px-3 py-2 cursor-pointer transition-colors ${
                isSelected
                  ? "bg-[var(--color-bg-elevated)]"
                  : "hover:bg-[var(--color-bg-panel-2)]"
              }`}
              onClick={() => onSelect(ticker)}
              data-testid={`watchlist-row-${ticker}`}
              data-ticker={ticker}
            >
              <span className="mono text-sm font-semibold w-14 truncate">
                {ticker}
              </span>
              <div className="flex-1 flex justify-center">
                <Sparkline data={hist} width={70} height={20} />
              </div>
              <PriceCell
                price={update?.price}
                className="text-sm w-16 text-right"
                data-testid={`watchlist-price-${ticker}`}
              />
              <span className={`mono text-xs w-16 text-right ${pctClass}`}>
                {update ? formatPercent(pct) : "—"}
              </span>
              <button
                type="button"
                aria-label={`Remove ${ticker}`}
                data-testid={`watchlist-remove-${ticker}`}
                className="opacity-0 group-hover:opacity-100 text-[var(--color-text-muted)] hover:text-[var(--color-tick-down)] transition-opacity"
                onClick={(e) => {
                  e.stopPropagation();
                  void onRemove(ticker);
                }}
              >
                ×
              </button>
            </li>
          );
        })}
      </ul>

      <form
        onSubmit={submit}
        className="flex items-center gap-2 border-t border-[var(--color-border-subtle)] p-2"
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add ticker"
          data-testid="watchlist-add-input"
          className="mono flex-1 bg-[var(--color-bg-base)] border border-[var(--color-border-subtle)] rounded px-2 py-1 text-sm uppercase placeholder:normal-case placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent-blue)]"
          maxLength={6}
          disabled={busy}
        />
        <button
          type="submit"
          data-testid="watchlist-add-button"
          disabled={busy || !draft.trim()}
          className="text-xs uppercase tracking-wider px-3 py-1 rounded bg-[var(--color-accent-purple)] text-white disabled:opacity-40 hover:brightness-110 transition"
        >
          Add
        </button>
      </form>
      {error ? (
        <div className="px-3 pb-2 text-xs text-[var(--color-tick-down)]">
          {error}
        </div>
      ) : null}
    </div>
  );
}

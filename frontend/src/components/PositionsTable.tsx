"use client";

import { PriceCell } from "@/components/PriceCell";
import { formatNumber, formatPercent, formatSignedUsd, formatUsd } from "@/lib/format";
import type { PositionView, PriceUpdate } from "@/types/api";

type Props = {
  positions: PositionView[];
  prices: Record<string, PriceUpdate>;
};

/**
 * Tabular position view. Current-price column is driven by the live SSE
 * price feed (overrides the slightly-stale value from /api/portfolio).
 */
export function PositionsTable({ positions, prices }: Props) {
  return (
    <div className="panel flex flex-col h-full" data-testid="positions-table">
      <div className="panel-header">
        <span>Positions</span>
        <span className="text-[var(--color-text-muted)] normal-case tracking-normal">
          {positions.length} open
        </span>
      </div>
      <div className="flex-1 overflow-auto">
        {positions.length === 0 ? (
          <div className="p-4 text-sm text-[var(--color-text-muted)]">
            No open positions.
          </div>
        ) : (
          <table className="w-full text-xs mono">
            <thead className="text-[var(--color-text-muted)] uppercase tracking-wider">
              <tr className="border-b border-[var(--color-border-subtle)]">
                <th className="text-left px-3 py-2 font-medium">Ticker</th>
                <th className="text-right px-2 py-2 font-medium">Qty</th>
                <th className="text-right px-2 py-2 font-medium">Avg Cost</th>
                <th className="text-right px-2 py-2 font-medium">Last</th>
                <th className="text-right px-2 py-2 font-medium">P&amp;L</th>
                <th className="text-right px-3 py-2 font-medium">%</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => {
                const live = prices[p.ticker]?.price ?? p.current_price ?? p.avg_cost;
                const pl = (live - p.avg_cost) * p.quantity;
                const pct = p.avg_cost
                  ? ((live - p.avg_cost) / p.avg_cost) * 100
                  : 0;
                const plClass =
                  pl > 0
                    ? "text-[var(--color-tick-up)]"
                    : pl < 0
                      ? "text-[var(--color-tick-down)]"
                      : "text-[var(--color-text-secondary)]";
                return (
                  <tr
                    key={p.ticker}
                    data-testid={`position-row-${p.ticker}`}
                    className="border-b border-[var(--color-border-subtle)] last:border-0 hover:bg-[var(--color-bg-panel-2)]"
                  >
                    <td className="px-3 py-2 font-semibold">{p.ticker}</td>
                    <td className="text-right px-2 py-2">
                      {formatNumber(p.quantity)}
                    </td>
                    <td className="text-right px-2 py-2">
                      {formatUsd(p.avg_cost)}
                    </td>
                    <td className="text-right px-2 py-2">
                      <PriceCell price={live} />
                    </td>
                    <td className={`text-right px-2 py-2 ${plClass}`}>
                      {formatSignedUsd(pl)}
                    </td>
                    <td className={`text-right px-3 py-2 ${plClass}`}>
                      {formatPercent(pct)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

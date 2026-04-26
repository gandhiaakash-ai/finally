"use client";

import { useState } from "react";
import { useLivePrices } from "@/hooks/useLivePrices";
import { useWatchlist } from "@/hooks/useWatchlist";
import { usePortfolio, usePortfolioHistory } from "@/hooks/usePortfolio";
import { ConnectionDot } from "@/components/ConnectionDot";
import { WatchlistPanel } from "@/components/WatchlistPanel";
import { MainChart } from "@/components/MainChart";
import { PortfolioHeatmap } from "@/components/PortfolioHeatmap";
import { PnlChart } from "@/components/PnlChart";
import { PositionsTable } from "@/components/PositionsTable";
import { TradeBar } from "@/components/TradeBar";
import { ChatPanel } from "@/components/ChatPanel";
import { formatUsd } from "@/lib/format";

export default function Home() {
  const { prices, history, status } = useLivePrices();
  const { tickers, add, remove, refresh: refreshWatchlist } = useWatchlist();
  const { summary, refresh: refreshPortfolio } = usePortfolio();
  const { snapshots } = usePortfolioHistory();
  const [selected, setSelected] = useState<string | null>("AAPL");

  const activeTicker = selected ?? tickers[0] ?? null;

  return (
    <main className="min-h-screen flex flex-col p-4 gap-4">
      <header
        data-testid="app-header"
        className="flex items-center justify-between border-b border-[var(--color-border-subtle)] pb-3"
      >
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-sm bg-[var(--color-accent-yellow)] flex items-center justify-center">
            <span className="font-bold text-black">F</span>
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">
              FinAlly
              <span className="ml-2 text-[var(--color-text-muted)] text-xs uppercase tracking-widest">
                Trading Workstation
              </span>
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-6 text-xs">
          <ConnectionDot status={status} />
          <div className="flex items-baseline gap-2">
            <span className="text-[var(--color-text-muted)] uppercase tracking-widest">
              Total
            </span>
            <span
              data-testid="portfolio-total-value"
              className="mono text-[var(--color-text-primary)] text-base"
            >
              {summary ? formatUsd(summary.total_value) : "—"}
            </span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-[var(--color-text-muted)] uppercase tracking-widest">
              Cash
            </span>
            <span
              data-testid="cash-balance"
              className="mono text-[var(--color-text-primary)] text-base"
            >
              {summary ? formatUsd(summary.cash_balance) : "—"}
            </span>
          </div>
        </div>
      </header>

      <TradeBar defaultTicker={activeTicker} onTraded={refreshPortfolio} />

      <section className="grid grid-cols-12 gap-4 flex-1 min-h-[420px]">
        <div className="col-span-3 min-h-[420px]">
          <WatchlistPanel
            tickers={tickers}
            prices={prices}
            history={history}
            selected={activeTicker}
            onSelect={setSelected}
            onAdd={add}
            onRemove={remove}
          />
        </div>
        <div className="col-span-6 min-h-[420px]">
          <MainChart
            ticker={activeTicker}
            history={activeTicker ? history[activeTicker] ?? [] : []}
            latest={activeTicker ? prices[activeTicker] : undefined}
          />
        </div>
        <div className="col-span-3 min-h-[420px]">
          <ChatPanel
            onActions={() => {
              refreshPortfolio();
              refreshWatchlist();
            }}
          />
        </div>
      </section>

      <section className="grid grid-cols-12 gap-4 min-h-[240px]">
        <div className="col-span-4 min-h-[240px]">
          <PortfolioHeatmap positions={summary?.positions ?? []} />
        </div>
        <div className="col-span-4 min-h-[240px]">
          <PnlChart snapshots={snapshots} />
        </div>
        <div className="col-span-4 min-h-[240px]">
          <PositionsTable positions={summary?.positions ?? []} prices={prices} />
        </div>
      </section>
    </main>
  );
}

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PositionsTable } from "../PositionsTable";
import type { PositionView, PriceUpdate } from "@/types/api";

const position = (overrides: Partial<PositionView> = {}): PositionView => ({
  ticker: "AAPL",
  quantity: 5,
  avg_cost: 100,
  current_price: 110,
  market_value: 550,
  unrealized_pl: 50,
  unrealized_pl_percent: 10,
  ...overrides,
});

const price = (ticker: string, p: number): PriceUpdate => ({
  ticker,
  price: p,
  previous_price: p - 1,
  timestamp: 0,
  change: 1,
  change_percent: 1,
  direction: "up",
});

describe("PositionsTable", () => {
  it("shows an empty state when there are no positions", () => {
    render(<PositionsTable positions={[]} prices={{}} />);
    expect(screen.getByText("No open positions.")).toBeInTheDocument();
  });

  it("renders one row per position with the test ID", () => {
    render(
      <PositionsTable
        positions={[position(), position({ ticker: "NVDA", avg_cost: 800 })]}
        prices={{}}
      />,
    );
    expect(screen.getByTestId("position-row-AAPL")).toBeInTheDocument();
    expect(screen.getByTestId("position-row-NVDA")).toBeInTheDocument();
  });

  it("uses live price from SSE over server-side current_price", () => {
    render(
      <PositionsTable
        positions={[position()]}
        prices={{ AAPL: price("AAPL", 150) }}
      />,
    );
    // Live = 150, avg = 100, qty = 5 => P&L = +$250.00, %=+50.00%
    expect(screen.getByText("+$250.00")).toBeInTheDocument();
    expect(screen.getByText("+50.00%")).toBeInTheDocument();
  });

  it("shows red P&L when below cost", () => {
    render(
      <PositionsTable
        positions={[position({ avg_cost: 200 })]}
        prices={{ AAPL: price("AAPL", 150) }}
      />,
    );
    expect(screen.getByText("-$250.00")).toBeInTheDocument();
  });
});

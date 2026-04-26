import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WatchlistPanel } from "../WatchlistPanel";
import type { PriceUpdate } from "@/types/api";

const mkPrice = (ticker: string, price: number, pct = 0.5): PriceUpdate => ({
  ticker,
  price,
  previous_price: price - 1,
  timestamp: 0,
  change: 1,
  change_percent: pct,
  direction: "up",
});

describe("WatchlistPanel", () => {
  const baseProps = {
    tickers: ["AAPL", "GOOGL"],
    prices: { AAPL: mkPrice("AAPL", 190.5), GOOGL: mkPrice("GOOGL", 175.0, -0.4) },
    history: { AAPL: [188, 189, 190.5], GOOGL: [177, 175] },
    selected: "AAPL",
    onSelect: vi.fn(),
    onAdd: vi.fn(),
    onRemove: vi.fn(),
  };

  it("renders one row per ticker with the test ID", () => {
    render(<WatchlistPanel {...baseProps} />);
    expect(screen.getByTestId("watchlist-row-AAPL")).toBeInTheDocument();
    expect(screen.getByTestId("watchlist-row-GOOGL")).toBeInTheDocument();
  });

  it("shows latest price and percent change with sign", () => {
    render(<WatchlistPanel {...baseProps} />);
    expect(screen.getByTestId("watchlist-price-AAPL")).toHaveTextContent("190.50");
    expect(screen.getByText("+0.50%")).toBeInTheDocument();
    expect(screen.getByText("-0.40%")).toBeInTheDocument();
  });

  it("calls onSelect when a row is clicked", () => {
    const onSelect = vi.fn();
    render(<WatchlistPanel {...baseProps} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("watchlist-row-GOOGL"));
    expect(onSelect).toHaveBeenCalledWith("GOOGL");
  });

  it("invokes onAdd from the form and clears the input", async () => {
    const onAdd = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<WatchlistPanel {...baseProps} onAdd={onAdd} />);
    await user.type(screen.getByTestId("watchlist-add-input"), "tsla");
    await user.click(screen.getByTestId("watchlist-add-button"));
    await waitFor(() => expect(onAdd).toHaveBeenCalledWith("TSLA"));
  });

  it("invokes onRemove from the row", () => {
    const onRemove = vi.fn();
    render(<WatchlistPanel {...baseProps} onRemove={onRemove} />);
    fireEvent.click(screen.getByTestId("watchlist-remove-AAPL"));
    expect(onRemove).toHaveBeenCalledWith("AAPL");
  });

  it("surfaces add errors inline", async () => {
    const onAdd = vi.fn().mockRejectedValue(new Error("Invalid ticker"));
    const user = userEvent.setup();
    render(<WatchlistPanel {...baseProps} onAdd={onAdd} />);
    await user.type(screen.getByTestId("watchlist-add-input"), "ZZZ");
    await user.click(screen.getByTestId("watchlist-add-button"));
    expect(await screen.findByText("Invalid ticker")).toBeInTheDocument();
  });
});

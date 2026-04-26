import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TradeBar } from "../TradeBar";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

const okTrade = {
  trade: {
    id: "t1",
    ticker: "AAPL",
    side: "buy",
    quantity: 1,
    price: 190.5,
    executed_at: "2026-04-26T00:00:00Z",
  },
  portfolio: { cash_balance: 0, positions: [], positions_value: 0, total_value: 0, total_cost_basis: 0, total_unrealized_pl: 0 },
};

describe("TradeBar", () => {
  it("validates ticker is required", async () => {
    render(<TradeBar />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId("trade-buy-button"));
    expect(await screen.findByText("Ticker is required")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("validates quantity must be positive", async () => {
    render(<TradeBar defaultTicker="AAPL" />);
    const user = userEvent.setup();
    const qty = screen.getByTestId("trade-qty-input");
    await user.clear(qty);
    await user.type(qty, "0");
    await user.click(screen.getByTestId("trade-buy-button"));
    expect(await screen.findByText("Quantity must be positive")).toBeInTheDocument();
  });

  it("submits a buy and shows confirmation", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(okTrade), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const onTraded = vi.fn();
    render(<TradeBar defaultTicker="AAPL" onTraded={onTraded} />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId("trade-buy-button"));
    expect(await screen.findByText(/Bought 1 AAPL/)).toBeInTheDocument();
    expect(onTraded).toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/portfolio/trade",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("surfaces server validation errors", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Insufficient cash" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      }),
    );
    render(<TradeBar defaultTicker="AAPL" />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId("trade-buy-button"));
    await waitFor(() =>
      expect(screen.getByText("Insufficient cash")).toBeInTheDocument(),
    );
  });
});

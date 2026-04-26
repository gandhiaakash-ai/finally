import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatPanel } from "../ChatPanel";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

const reply = (overrides: object = {}) =>
  new Response(
    JSON.stringify({
      message: "Here is a summary.",
      trades: [],
      watchlist_changes: [],
      ...overrides,
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );

describe("ChatPanel", () => {
  it("renders the empty-state hints initially", () => {
    render(<ChatPanel />);
    expect(
      screen.getByText(/Ask anything — FinAlly can analyze positions/),
    ).toBeInTheDocument();
  });

  it("sends a message and renders both turns", async () => {
    fetchMock.mockResolvedValue(reply());
    render(<ChatPanel />);
    const user = userEvent.setup();
    await user.type(screen.getByTestId("chat-input"), "Hi");
    await user.click(screen.getByTestId("chat-send-button"));

    await waitFor(() =>
      expect(screen.getByText("Here is a summary.")).toBeInTheDocument(),
    );
    expect(screen.getAllByTestId("chat-message-user")).toHaveLength(1);
    expect(screen.getAllByTestId("chat-message-assistant")).toHaveLength(1);
  });

  it("renders trade and watchlist confirmation chips inline", async () => {
    fetchMock.mockResolvedValue(
      reply({
        trades: [
          {
            ticker: "AAPL",
            side: "buy",
            quantity: 5,
            price: 190.5,
            status: "filled",
            error: null,
          },
        ],
        watchlist_changes: [
          { ticker: "PYPL", action: "add", status: "applied", error: null },
        ],
      }),
    );
    render(<ChatPanel />);
    const user = userEvent.setup();
    await user.type(screen.getByTestId("chat-input"), "buy 5 AAPL");
    await user.click(screen.getByTestId("chat-send-button"));
    await waitFor(() =>
      expect(screen.getAllByTestId("chat-action-confirm")).toHaveLength(2),
    );
    expect(screen.getByText(/Bought 5 AAPL/)).toBeInTheDocument();
    expect(screen.getByText(/PYPL watchlist/)).toBeInTheDocument();
  });

  it("renders failed-trade chip with the user-safe error message", async () => {
    fetchMock.mockResolvedValue(
      reply({
        trades: [
          {
            ticker: "AAPL",
            side: "buy",
            quantity: 5000,
            price: null,
            status: "failed",
            error: "Insufficient cash: need $189,960.00, have $9,050.20",
          },
        ],
      }),
    );
    render(<ChatPanel />);
    const user = userEvent.setup();
    await user.type(screen.getByTestId("chat-input"), "buy 5000 AAPL");
    await user.click(screen.getByTestId("chat-send-button"));
    const chip = await screen.findByTestId("chat-action-confirm");
    expect(chip).toHaveTextContent(
      /Failed buy AAPL: Insufficient cash: need \$189,960\.00/,
    );
  });

  it("shows the loading indicator during a request", async () => {
    let resolveFetch: (r: Response) => void = () => {};
    fetchMock.mockReturnValue(
      new Promise<Response>((resolve) => {
        resolveFetch = resolve;
      }),
    );
    render(<ChatPanel />);
    const user = userEvent.setup();
    await user.type(screen.getByTestId("chat-input"), "Hi");
    await user.click(screen.getByTestId("chat-send-button"));
    expect(screen.getByText(/FinAlly is thinking/)).toBeInTheDocument();
    resolveFetch(reply());
    await waitFor(() =>
      expect(screen.queryByText(/FinAlly is thinking/)).not.toBeInTheDocument(),
    );
  });

  it("calls onActions when the response includes actions", async () => {
    fetchMock.mockResolvedValue(
      reply({
        trades: [
          { ticker: "AAPL", side: "buy", quantity: 1, price: 1, status: "filled", error: null },
        ],
      }),
    );
    const onActions = vi.fn();
    render(<ChatPanel onActions={onActions} />);
    const user = userEvent.setup();
    await user.type(screen.getByTestId("chat-input"), "Buy");
    await user.click(screen.getByTestId("chat-send-button"));
    await waitFor(() => expect(onActions).toHaveBeenCalled());
  });
});

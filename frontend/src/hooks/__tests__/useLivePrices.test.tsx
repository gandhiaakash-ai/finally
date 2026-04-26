/**
 * Tests for useLivePrices — uses a fake EventSource implementation to
 * simulate the SSE stream without hitting the network.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  readyState = 0;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  open() {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }

  emit(payload: unknown) {
    this.onmessage?.(
      new MessageEvent("message", { data: JSON.stringify(payload) }),
    );
  }

  error() {
    this.onerror?.(new Event("error"));
  }

  close() {
    this.readyState = 2;
  }
}

beforeEach(() => {
  FakeEventSource.instances = [];
  // Install fake EventSource on globalThis (jsdom doesn't provide one).
  vi.stubGlobal("EventSource", FakeEventSource);
});

import { useLivePrices } from "../useLivePrices";

const mkUpdate = (ticker: string, price: number) => ({
  ticker,
  price,
  previous_price: price,
  timestamp: 0,
  change: 0,
  change_percent: 0,
  direction: "flat" as const,
});

describe("useLivePrices", () => {
  it("starts disconnected and reaches connected after open", () => {
    const { result } = renderHook(() => useLivePrices());
    expect(["disconnected", "reconnecting"]).toContain(result.current.status);

    act(() => {
      FakeEventSource.instances[0]!.open();
    });
    expect(result.current.status).toBe("connected");
  });

  it("updates price map and accumulates history on each tick", () => {
    const { result } = renderHook(() => useLivePrices());
    act(() => FakeEventSource.instances[0]!.open());

    act(() => {
      FakeEventSource.instances[0]!.emit({ AAPL: mkUpdate("AAPL", 190.5) });
    });
    expect(result.current.prices.AAPL?.price).toBe(190.5);
    expect(result.current.history.AAPL).toEqual([190.5]);

    act(() => {
      FakeEventSource.instances[0]!.emit({ AAPL: mkUpdate("AAPL", 191.25) });
    });
    expect(result.current.prices.AAPL?.price).toBe(191.25);
    expect(result.current.history.AAPL).toEqual([190.5, 191.25]);
  });

  it("does not duplicate identical prices in history", () => {
    const { result } = renderHook(() => useLivePrices());
    act(() => FakeEventSource.instances[0]!.open());
    act(() => {
      FakeEventSource.instances[0]!.emit({ AAPL: mkUpdate("AAPL", 100) });
    });
    act(() => {
      FakeEventSource.instances[0]!.emit({ AAPL: mkUpdate("AAPL", 100) });
    });
    expect(result.current.history.AAPL).toEqual([100]);
  });

  it("transitions to reconnecting on error", () => {
    const { result } = renderHook(() => useLivePrices());
    act(() => FakeEventSource.instances[0]!.open());
    expect(result.current.status).toBe("connected");

    act(() => FakeEventSource.instances[0]!.error());
    expect(result.current.status).toBe("reconnecting");
  });

  it("ignores malformed payloads without crashing", () => {
    const { result } = renderHook(() => useLivePrices());
    act(() => FakeEventSource.instances[0]!.open());
    act(() => {
      FakeEventSource.instances[0]!.onmessage?.(
        new MessageEvent("message", { data: "not json" }),
      );
    });
    // No crash; price map remains empty.
    expect(result.current.prices).toEqual({});
  });
});

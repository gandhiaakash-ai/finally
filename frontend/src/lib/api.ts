/**
 * API client — calls same-origin /api/* (no CORS, no env).
 * The static export is served by FastAPI from "/", so relative paths just work.
 */
import type {
  ChatRequest,
  ChatResult,
  PortfolioHistoryResponse,
  PortfolioSummary,
  TradeRequest,
  TradeResponse,
  WatchlistListResponse,
  WatchlistMutationResponse,
} from "@/types/api";

const API = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string; error?: string };
      detail = body.detail ?? body.error ?? detail;
    } catch {
      // body wasn't JSON; keep statusText
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export const api = {
  getPortfolio: () => request<PortfolioSummary>("/portfolio"),
  getPortfolioHistory: () =>
    request<PortfolioHistoryResponse>("/portfolio/history"),
  trade: (body: TradeRequest) =>
    request<TradeResponse>("/portfolio/trade", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getWatchlist: () => request<WatchlistListResponse>("/watchlist"),
  addWatchlist: (ticker: string) =>
    request<WatchlistMutationResponse>("/watchlist", {
      method: "POST",
      body: JSON.stringify({ ticker }),
    }),
  removeWatchlist: (ticker: string) =>
    request<WatchlistMutationResponse>(
      `/watchlist/${encodeURIComponent(ticker)}`,
      { method: "DELETE" },
    ),
  chat: (body: ChatRequest) =>
    request<ChatResult>("/chat", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

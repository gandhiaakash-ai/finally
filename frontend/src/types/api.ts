/**
 * Shared API types — mirrors backend response shapes.
 * Sourced from backend/app/routes/* and backend/app/portfolio/* (verified).
 */

export type TradeSide = "buy" | "sell";
export type PriceDirection = "up" | "down" | "flat";

export interface PriceUpdate {
  ticker: string;
  price: number;
  previous_price: number;
  /** Unix seconds (float) — matches backend `time.time()` */
  timestamp: number;
  change: number;
  change_percent: number;
  direction: PriceDirection;
}

export interface PositionView {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number | null;
  market_value: number;
  unrealized_pl: number;
  unrealized_pl_percent: number;
}

export interface PortfolioSummary {
  cash_balance: number;
  positions: PositionView[];
  positions_value: number;
  total_value: number;
  total_cost_basis: number;
  total_unrealized_pl: number;
}

export interface TradeRequest {
  ticker: string;
  quantity: number;
  side: TradeSide;
}

export interface TradeRecord {
  id: string;
  ticker: string;
  side: TradeSide;
  quantity: number;
  price: number;
  executed_at: string;
}

export interface TradeResponse {
  trade: TradeRecord;
  portfolio: PortfolioSummary;
}

export interface WatchlistEntry {
  ticker: string;
  /** Latest price update from cache, or null if no tick yet. */
  price: PriceUpdate | null;
}

export interface WatchlistListResponse {
  tickers: WatchlistEntry[];
}

export interface WatchlistMutationResponse {
  ticker: string;
  added?: boolean;
  removed?: boolean;
  /** New flat ticker list. */
  tickers: string[];
}

export interface PortfolioSnapshot {
  id: string;
  total_value: number;
  recorded_at: string;
}

export interface PortfolioHistoryResponse {
  snapshots: PortfolioSnapshot[];
}

export interface ExecutedTrade {
  ticker: string;
  side: TradeSide;
  quantity: number;
  price: number | null;
  status: "filled" | "failed";
  error: string | null;
}

export interface AppliedWatchlistChange {
  ticker: string;
  action: "add" | "remove";
  status: "applied" | "failed";
  error: string | null;
}

export interface ChatRequest {
  message: string;
}

export interface ChatResult {
  message: string;
  trades: ExecutedTrade[];
  watchlist_changes: AppliedWatchlistChange[];
}

/**
 * Shared selector contract between frontend and E2E tests.
 *
 * The frontend MUST attach these `data-testid` attributes for the suite
 * to work. Discuss any changes before renaming.
 */
export const tid = {
  // Header
  header: "app-header",
  cashBalance: "cash-balance",
  totalValue: "portfolio-total-value",
  connectionStatus: "connection-status",

  // Watchlist
  watchlist: "watchlist",
  watchlistRow: (ticker: string) => `watchlist-row-${ticker}`,
  watchlistPrice: (ticker: string) => `watchlist-price-${ticker}`,
  watchlistRemove: (ticker: string) => `watchlist-remove-${ticker}`,
  watchlistAddInput: "watchlist-add-input",
  watchlistAddButton: "watchlist-add-button",

  // Trade bar
  tradeTicker: "trade-ticker-input",
  tradeQty: "trade-qty-input",
  tradeBuy: "trade-buy-button",
  tradeSell: "trade-sell-button",

  // Positions / portfolio
  positionsTable: "positions-table",
  positionRow: (ticker: string) => `position-row-${ticker}`,
  heatmap: "portfolio-heatmap",
  heatmapTile: (ticker: string) => `heatmap-tile-${ticker}`,
  pnlChart: "pnl-chart",

  // Chat
  chatPanel: "chat-panel",
  chatInput: "chat-input",
  chatSend: "chat-send-button",
  chatMessage: "chat-message",
  chatMessageRole: (role: "user" | "assistant") => `chat-message-${role}`,
  chatActionConfirm: "chat-action-confirm",
} as const;

export const sel = {
  byTid: (id: string) => `[data-testid="${id}"]`,
};

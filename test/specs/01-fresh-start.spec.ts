import { expect, test } from "@playwright/test";
import { sel, tid } from "../support/selectors";
import { DEFAULT_WATCHLIST, resetState } from "../support/api";

test.describe("fresh start", () => {
  test.beforeEach(async ({ request }) => {
    await resetState(request);
  });

  test("default watchlist, $10k-class cash, prices stream", async ({ page }) => {
    await page.goto("/");

    // All 10 default tickers are visible in the watchlist
    for (const ticker of DEFAULT_WATCHLIST) {
      await expect(page.locator(sel.byTid(tid.watchlistRow(ticker)))).toBeVisible();
    }

    // Cash balance shows the starting $10,000 (formatted with separators)
    const cash = page.locator(sel.byTid(tid.cashBalance));
    await expect(cash).toBeVisible();
    await expect(cash).toContainText(/10[,.\s]?000(\.00)?/);

    // Connection status indicates a live stream
    const status = page.locator(sel.byTid(tid.connectionStatus));
    await expect(status).toBeVisible();
    await expect(status).toHaveAttribute("data-status", /connected|live/);

    // Prices stream — sample one ticker and assert its rendered price changes
    const priceCell = page.locator(sel.byTid(tid.watchlistPrice("AAPL")));
    await expect(priceCell).toBeVisible();
    const initial = (await priceCell.textContent())?.trim() ?? "";
    await expect.poll(
      async () => (await priceCell.textContent())?.trim() ?? "",
      { timeout: 15_000, intervals: [500, 1000] },
    ).not.toBe(initial);
  });
});

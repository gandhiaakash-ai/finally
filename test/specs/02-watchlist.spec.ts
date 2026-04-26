import { expect, test } from "@playwright/test";
import { sel, tid } from "../support/selectors";
import { resetState } from "../support/api";

test.describe("watchlist add / remove", () => {
  test.beforeEach(async ({ request }) => {
    await resetState(request);
  });

  test("add a ticker, see it stream, then remove it", async ({ page }) => {
    await page.goto("/");

    const ticker = "PYPL";
    await page.locator(sel.byTid(tid.watchlistAddInput)).fill(ticker);
    await page.locator(sel.byTid(tid.watchlistAddButton)).click();

    const row = page.locator(sel.byTid(tid.watchlistRow(ticker)));
    await expect(row).toBeVisible();

    // Streaming price renders for the new ticker (non-empty number-ish text)
    const priceCell = page.locator(sel.byTid(tid.watchlistPrice(ticker)));
    await expect(priceCell).toBeVisible();
    await expect.poll(
      async () => (await priceCell.textContent())?.trim() ?? "",
      { timeout: 15_000 },
    ).toMatch(/\d+(\.\d+)?/);

    // Remove the ticker — row disappears
    await page.locator(sel.byTid(tid.watchlistRemove(ticker))).click();
    await expect(row).toBeHidden();
  });
});

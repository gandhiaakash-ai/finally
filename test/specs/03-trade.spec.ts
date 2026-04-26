import { expect, test } from "@playwright/test";
import { sel, tid } from "../support/selectors";
import { getPortfolio, resetState } from "../support/api";

test.describe("buy and sell", () => {
  test.beforeEach(async ({ request }) => {
    await resetState(request);
  });

  test("buy decreases cash and creates a position; sell removes it", async ({ page, request }) => {
    await page.goto("/");

    const ticker = "AAPL";
    const cashLocator = page.locator(sel.byTid(tid.cashBalance));
    const cashBefore = parseMoney(await cashLocator.textContent());

    // Buy 5 shares
    await page.locator(sel.byTid(tid.tradeTicker)).fill(ticker);
    await page.locator(sel.byTid(tid.tradeQty)).fill("5");
    await page.locator(sel.byTid(tid.tradeBuy)).click();

    // Position row appears. The row text concatenates cells without
    // separators (e.g. "AAPL5$190.17..."); we verify the quantity via
    // the API below rather than a brittle regex on rendered text.
    const posRow = page.locator(sel.byTid(tid.positionRow(ticker)));
    await expect(posRow).toBeVisible();

    // Cash decreased
    await expect.poll(
      async () => parseMoney(await cashLocator.textContent()),
      { timeout: 10_000 },
    ).toBeLessThan(cashBefore);

    const portfolioAfterBuy = await getPortfolio(request);
    expect(portfolioAfterBuy.cash_balance).toBeLessThan(cashBefore);
    expect(
      (portfolioAfterBuy.positions ?? []).find((p: any) => p.ticker === ticker)?.quantity,
    ).toBe(5);

    // Sell all 5 shares
    await page.locator(sel.byTid(tid.tradeTicker)).fill(ticker);
    await page.locator(sel.byTid(tid.tradeQty)).fill("5");
    await page.locator(sel.byTid(tid.tradeSell)).click();

    // Position disappears or shows zero
    await expect.poll(async () => {
      const portfolio = await getPortfolio(request);
      const pos = (portfolio.positions ?? []).find((p: any) => p.ticker === ticker);
      return pos?.quantity ?? 0;
    }, { timeout: 10_000 }).toBe(0);

    // Cash recovered (back above pre-buy minus a small simulator drift; we
    // just assert it's higher than the post-buy snapshot)
    await expect.poll(
      async () => parseMoney(await cashLocator.textContent()),
      { timeout: 10_000 },
    ).toBeGreaterThan(portfolioAfterBuy.cash_balance);
  });
});

function parseMoney(text: string | null): number {
  if (!text) return Number.NaN;
  const cleaned = text.replace(/[^0-9.\-]/g, "");
  return Number.parseFloat(cleaned);
}

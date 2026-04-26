import { expect, test } from "@playwright/test";
import { sel, tid } from "../support/selectors";
import { resetState, trade } from "../support/api";

test.describe("portfolio visualizations", () => {
  test.beforeEach(async ({ request }) => {
    await resetState(request);
    // Seed two positions so the heatmap has something to draw
    await trade(request, { ticker: "AAPL", side: "buy", quantity: 3 });
    await trade(request, { ticker: "MSFT", side: "buy", quantity: 2 });
  });

  test("heatmap has tiles and P&L chart accumulates points", async ({ page }) => {
    await page.goto("/");

    const heatmap = page.locator(sel.byTid(tid.heatmap));
    await expect(heatmap).toBeVisible();
    await expect(page.locator(sel.byTid(tid.heatmapTile("AAPL")))).toBeVisible();
    await expect(page.locator(sel.byTid(tid.heatmapTile("MSFT")))).toBeVisible();

    // P&L chart container is rendered
    const pnl = page.locator(sel.byTid(tid.pnlChart));
    await expect(pnl).toBeVisible();

    // Chart accumulates at least one drawn data point — implementations
    // differ (svg path, canvas), so we accept either:
    //   - an <svg path> with non-empty `d` attribute, OR
    //   - a <canvas> with non-zero size.
    await expect.poll(async () => {
      return await pnl.evaluate((el) => {
        const path = el.querySelector("svg path");
        if (path && (path.getAttribute("d") ?? "").length > 0) return true;
        const canvas = el.querySelector("canvas") as HTMLCanvasElement | null;
        if (canvas && canvas.width > 0 && canvas.height > 0) return true;
        return false;
      });
    }, { timeout: 30_000 }).toBeTruthy();
  });
});

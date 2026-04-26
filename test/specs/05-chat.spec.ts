import { expect, test } from "@playwright/test";
import { sel, tid } from "../support/selectors";
import { getPortfolio, resetState } from "../support/api";

/**
 * The mock LLM (LLM_MOCK=true) produces deterministic structured output.
 * We rely on the contract documented in PLAN.md §9: when the user asks
 * to buy a ticker, the mock returns a `trades` action and the backend
 * auto-executes it. The frontend renders the assistant's `message` and
 * an inline confirmation for each executed action.
 */
test.describe("AI chat (mocked)", () => {
  test.beforeEach(async ({ request }) => {
    await resetState(request);
  });

  test("send a message, see assistant reply and inline trade confirmation", async ({ page, request }) => {
    await page.goto("/");

    const input = page.locator(sel.byTid(tid.chatInput));
    await expect(input).toBeVisible();
    await input.fill("buy 2 shares of AAPL");
    await page.locator(sel.byTid(tid.chatSend)).click();

    // User and assistant messages render
    const userMessages = page.locator(sel.byTid(tid.chatMessageRole("user")));
    const assistantMessages = page.locator(sel.byTid(tid.chatMessageRole("assistant")));
    await expect(userMessages.last()).toContainText(/buy 2 shares of AAPL/i);
    await expect(assistantMessages.last()).toBeVisible({ timeout: 30_000 });

    // Inline confirmation of the executed trade is shown alongside the
    // assistant message
    const confirm = page.locator(sel.byTid(tid.chatActionConfirm));
    await expect(confirm.last()).toBeVisible();
    await expect(confirm.last()).toContainText(/AAPL/);

    // Backend reflects the auto-executed trade
    await expect.poll(async () => {
      const portfolio = await getPortfolio(request);
      return (portfolio.positions ?? []).find((p: any) => p.ticker === "AAPL")?.quantity ?? 0;
    }, { timeout: 15_000 }).toBeGreaterThan(0);
  });
});

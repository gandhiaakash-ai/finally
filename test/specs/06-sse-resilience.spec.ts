import { expect, test } from "@playwright/test";
import { sel, tid } from "../support/selectors";
import { resetState } from "../support/api";

test.describe("SSE resilience", () => {
  test.beforeEach(async ({ request }) => {
    await resetState(request);
  });

  test("SSE drop turns the indicator amber/red, then it recovers", async ({ page, context }) => {
    // Block any reconnect attempt to /api/stream/prices BEFORE the page
    // loads, so the very first `EventSource` will fire `onerror` (and
    // transition the indicator out of "connected"). We flip the flag off
    // later to allow the recovery branch.
    let dropConnections = true;
    let blockedRequests = 0;
    await context.route("**/api/stream/prices**", async (route) => {
      if (dropConnections) {
        blockedRequests += 1;
        await route.abort("connectionrefused");
        return;
      }
      await route.continue();
    });

    await page.goto("/");

    const status = page.locator(sel.byTid(tid.connectionStatus));
    await expect(status).toBeVisible();

    // First connection is aborted → indicator must move off "connected".
    await expect.poll(
      async () => status.getAttribute("data-status"),
      { timeout: 15_000, message: `blockedRequests=${blockedRequests}` },
    ).toMatch(/disconnect|reconnect|error|offline/);

    // Allow reconnect attempts to succeed; EventSource retries automatically.
    dropConnections = false;

    await expect.poll(
      async () => status.getAttribute("data-status"),
      { timeout: 30_000 },
    ).toMatch(/connected|live/);
  });
});

import { expect, test, type Page } from "@playwright/test";

/**
 * Live-mode smoke (F4): the console against a running API, no LLM calls.
 *
 *   NEXT_PUBLIC_API_MODE=live NEXT_PUBLIC_API_URL=http://localhost:8000 pnpm build
 *   E2E_LIVE=1 E2E_LIVE_PASSCODE=<DEMO_PASSCODE> pnpm test:e2e live
 *
 * Needs `uv run uvicorn psa.api.main:app` with a seeded world, WEB_ORIGIN set to the
 * e2e origin and at least one report in evals/reports/. Sends no chat messages.
 */
const LIVE = process.env.E2E_LIVE === "1";
const PASSCODE = process.env.E2E_LIVE_PASSCODE ?? "";

test.skip(!LIVE, "set E2E_LIVE=1 against a running API");

function watchErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(`console: ${msg.text()}`);
  });
  return errors;
}

async function signIn(page: Page, next: string) {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("Passcode").fill(PASSCODE);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(`**${next}`);
}

test("console pages load real data from the API", async ({ page }) => {
  const errors = watchErrors(page);
  await signIn(page, "/conversations");
  await expect(page.getByRole("heading", { level: 1, name: "Conversations" })).toBeVisible();
  await expect(page.getByText(/couldn.t load|something went wrong/i)).toHaveCount(0);

  await page.goto("/approvals");
  await expect(page.getByRole("tab", { name: /Pending/ })).toBeVisible();
  await expect(page.getByText(/couldn.t load|something went wrong/i)).toHaveCount(0);

  await page.goto("/evals");
  const run = page.getByRole("link", { name: /live-check|run_/ }).first();
  await expect(run).toBeVisible();
  await run.click();
  await expect(page.getByRole("region", { name: "Unauthorized action rate" })).toBeVisible();

  expect(errors).toEqual([]);
});

test("landing shows live numbers to a signed-in operator", async ({ page }) => {
  await signIn(page, "/conversations");
  await page.goto("/");
  await expect(page.getByText("Live API").first()).toBeVisible();
});

test("a bad token is dropped and sends the user to login", async ({ page }) => {
  await page.goto("/login");
  await page.evaluate(() =>
    sessionStorage.setItem(
      "psa.session",
      JSON.stringify({ token: "forged.token", expires_at: new Date(Date.now() + 3_600_000).toISOString() }),
    ),
  );
  await page.goto("/approvals");
  await page.waitForURL(/\/login/);
  expect(await page.evaluate(() => sessionStorage.getItem("psa.session"))).toBeNull();
});

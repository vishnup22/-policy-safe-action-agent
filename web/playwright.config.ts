import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.E2E_PORT ?? 3100);
const BASE_URL = process.env.E2E_BASE_URL ?? `http://127.0.0.1:${PORT}`;
/** Set PW_CHANNEL=chrome to use an installed Chrome instead of Playwright's bundled Chromium. */
const channel = process.env.PW_CHANNEL || undefined;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  // One `next start` server backs every worker; more than a few starves it.
  workers: process.env.CI ? 2 : 4,
  timeout: 60_000,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    channel,
  },
  projects: [
    { name: "mobile-375", use: { ...devices["Desktop Chrome"], channel, viewport: { width: 375, height: 812 }, hasTouch: true } },
    { name: "desktop-1440", use: { ...devices["Desktop Chrome"], channel, viewport: { width: 1440, height: 900 } } },
  ],
  // Runs against the production build (`pnpm build` first) in mock mode.
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: `pnpm start --port ${PORT}`,
        url: BASE_URL,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});

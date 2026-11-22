import { expect, test, type Page } from "@playwright/test";

const PASSCODE = process.env.NEXT_PUBLIC_MOCK_PASSCODE || "larkspur-demo";

/** Fails the test on uncaught exceptions or console errors. */
function watchErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(`console: ${msg.text()}`);
  });
  return errors;
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page scrolls horizontally").toBeLessThanOrEqual(1);
}

async function signIn(page: Page, next = "/chat") {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("Passcode").fill(PASSCODE);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(`**${next}`);
}

async function goTo(page: Page, label: "Chat" | "Conversations" | "Approvals" | "Evals") {
  const isMobile = (page.viewportSize()?.width ?? 1440) < 768;
  if (isMobile) {
    await page.getByRole("button", { name: "Open navigation" }).click();
    await page.getByRole("dialog").getByRole("link", { name: new RegExp(`^${label}`) }).click();
  } else {
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: new RegExp(`^${label}`) }).click();
  }
}

test.describe("landing page", () => {
  test("hero, live-or-mock results, bento and dock render without errors", async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: /Agents that can act/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /View on GitHub/ })).toBeVisible();

    const results = page.getByRole("article", { name: "Baseline vs guarded" });
    await results.scrollIntoViewIfNeeded();
    await expect(results.getByText("Demo data")).toBeVisible();
    await expect(results.getByText(/^\d+(\.\d)?%$/).first()).toBeVisible();
    for (const name of ["Propose → decide → execute", "pass^k — reliability", "Replay a decision", "Policy as code", "Human in the loop"]) {
      await expect(page.getByRole("article", { name })).toBeAttached();
    }

    const dock = page.getByRole("navigation", { name: "Footer" });
    await dock.scrollIntoViewIfNeeded();
    await expect(dock.getByRole("link", { name: "Eval runs" })).toBeVisible();
    await expectNoHorizontalOverflow(page);
    expect(errors).toEqual([]);
  });

  test("section nav is a floating pill on desktop and collapses on mobile", async ({ page }) => {
    await page.goto("/");
    const sections = page.getByRole("navigation", { name: "Sections" });
    if ((page.viewportSize()?.width ?? 0) >= 768) {
      await expect(sections).toBeVisible();
      await expect(page.getByRole("article", { name: "Baseline vs guarded" })).toBeAttached();
      await sections.getByRole("link", { name: "Results" }).click();
      await expect(sections.getByRole("link", { name: "Results" })).toHaveAttribute("aria-current", "location");
    } else {
      await expect(sections).toBeHidden();
    }
  });

  test("Open console goes through sign-in", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("banner").getByRole("link", { name: /Open console/ }).click();
    await page.waitForURL(/\/login\?next=%2Fchat/);
    await expect(page.getByLabel("Passcode")).toBeVisible();
  });

  test("reduced motion stops the aurora and the shimmer", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const page = await context.newPage();
    await page.goto("/");
    const blobAnimation = await page.locator(".aurora-blob").first().evaluate((el) => getComputedStyle(el).animationName);
    const shimmerAnimation = await page.locator(".shimmer-sweep").evaluate((el) => getComputedStyle(el).animationName);
    expect(blobAnimation).toBe("none");
    expect(shimmerAnimation).toBe("none");
    await context.close();
  });
});

test.describe("console (mock mode)", () => {
  test("a wrong passcode is rejected", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Passcode").fill("nope");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("alert").filter({ hasText: /passcode/ })).toBeVisible();
    await expect(page.getByLabel("Passcode")).toHaveAttribute("aria-invalid", "true");
  });

  test("every console page works: chat → conversations → replay → approvals → evals", async ({ page }) => {
    const errors = watchErrors(page);
    await signIn(page);

    // Chat: a demo story produces an inline policy decision.
    await page.getByRole("button", { name: "Out-of-window refund" }).click();
    const card = page.getByRole("article", { name: /Proposed action: Issue refund/ });
    await expect(card).toBeVisible();
    await expect(card.locator('[data-outcome="DENY"]')).toBeVisible();
    await expectNoHorizontalOverflow(page);

    // Conversations → replay.
    await goTo(page, "Conversations");
    await expect(page.getByRole("heading", { level: 1, name: "Conversations" })).toBeVisible();
    await page.getByRole("link", { name: "conv_l4mp9q2w" }).click();
    await expect(page.getByRole("region", { name: "Event timeline" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Event detail" })).toBeVisible();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("region", { name: "Event detail" }).getByRole("heading", { name: "User message" })).toBeVisible();
    await expectNoHorizontalOverflow(page);

    // Approvals: open the drawer, then close it.
    await goTo(page, "Approvals");
    const pending = page.getByRole("list", { name: "pending approvals" });
    await pending.getByRole("button", { name: /Issue refund/ }).first().click();
    const drawer = page.getByRole("dialog");
    await expect(drawer.getByRole("button", { name: /Approve/ })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();
    await page.getByRole("tab", { name: /Rejected/ }).click();
    await expect(page.getByRole("list", { name: "rejected approvals" })).toBeVisible();
    await expectNoHorizontalOverflow(page);

    // Evals: list → report.
    await goTo(page, "Evals");
    await page.getByRole("link", { name: /run_20261121_1200/ }).click();
    await expect(page.getByRole("region", { name: "Unauthorized action rate" })).toBeVisible();
    await expect(page.getByRole("img", { name: /pass\^k line chart/ })).toBeVisible();
    await expectNoHorizontalOverflow(page);

    expect(errors).toEqual([]);
  });

  test("console nav pill marks the current page", async ({ page }) => {
    test.skip((page.viewportSize()?.width ?? 0) < 768, "desktop navigation only");
    await signIn(page, "/evals");
    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav.getByRole("link", { name: /^Evals/ })).toHaveAttribute("aria-current", "page");
    await nav.getByRole("link", { name: /^Approvals/ }).click();
    await expect(nav.getByRole("link", { name: /^Approvals/ })).toHaveAttribute("aria-current", "page");
  });
});

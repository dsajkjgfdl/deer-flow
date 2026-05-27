import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

test.describe("Landing page", () => {
  test("renders the header and hero section", async ({ page }) => {
    await page.goto("/landing");

    // Header brand name
    await expect(
      page.locator("header h1", { hasText: "DeerFlow" }),
    ).toBeVisible();

    // "Get Started" call-to-action button in hero
    await expect(
      page.getByRole("link", { name: /get started/i }),
    ).toBeVisible();
  });

  test("Get Started link navigates to workspace", async ({ page }) => {
    mockLangGraphAPI(page);

    await page.goto("/landing");

    const getStarted = page.getByRole("link", { name: /get started/i });
    await getStarted.click();

    // Should redirect to /workspace/chats/new
    await page.waitForURL("**/workspace/chats/new");
    await expect(page).toHaveURL(/\/workspace\/chats\/new/);
  });

  test("root route opens the new chat page", async ({ page }) => {
    mockLangGraphAPI(page);

    await page.goto("/");

    await page.waitForURL("**/workspace/chats/new");
    await expect(page).toHaveURL(/\/workspace\/chats\/new/);
    await expect(page.getByPlaceholder(/how can i assist you/i)).toBeVisible({
      timeout: 15_000,
    });
  });
});

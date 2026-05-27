import { describe, expect, test, vi } from "vitest";

const redirect = vi.fn((path: string) => {
  throw new Error(`NEXT_REDIRECT:${path}`);
});

vi.mock("next/navigation", () => ({
  redirect,
}));

async function loadHomePage() {
  vi.resetModules();
  redirect.mockClear();
  return await import("@/app/page");
}

describe("home page route", () => {
  test("redirects to the new chat page", async () => {
    const { default: HomePage } = await loadHomePage();

    expect(() => HomePage()).toThrow("NEXT_REDIRECT:/workspace/chats/new");
    expect(redirect).toHaveBeenCalledWith("/workspace/chats/new");
  });
});

import { describe, expect, rs, test } from "@rstest/core";

const redirect = rs.fn((path: string) => {
  throw new Error(`NEXT_REDIRECT:${path}`);
});

rs.mock("next/navigation", () => ({
  redirect,
}));

async function loadHomePage() {
  rs.resetModules();
  redirect.mockClear();
  return await import("@/app/page");
}

describe("home page route", () => {
  test(
    "redirects to the new chat page instead of rendering the landing navigation",
    async () => {
      const { default: HomePage } = await loadHomePage();

      expect(() => HomePage()).toThrow("NEXT_REDIRECT:/workspace/chats/new");
      expect(redirect).toHaveBeenCalledWith("/workspace/chats/new");
    },
    20_000,
  );
});

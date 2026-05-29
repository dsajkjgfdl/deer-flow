import { describe, expect, test, vi } from "vitest";

const redirect = vi.fn((path: string) => {
  throw new Error(`NEXT_REDIRECT:${path}`);
});

const getServerSideUser = vi.fn();

vi.mock("next/navigation", () => ({
  redirect,
}));

vi.mock("@/core/auth/server", () => ({
  getServerSideUser,
}));

vi.mock("@/components/workspace/admin/platform-admin-page", () => ({
  PlatformAdminPage: () => null,
}));

async function loadAdminPage() {
  vi.resetModules();
  redirect.mockClear();
  return await import("@/app/workspace/admin/page");
}

describe("workspace admin page route", () => {
  test("redirects normal users away from the admin page", async () => {
    getServerSideUser.mockResolvedValue({
      tag: "authenticated",
      user: {
        id: "user-1",
        email: "user@example.com",
        system_role: "user",
        needs_setup: false,
      },
    });
    const { default: WorkspaceAdminPage } = await loadAdminPage();

    await expect(Promise.resolve(WorkspaceAdminPage())).rejects.toThrow(
      "NEXT_REDIRECT:/workspace/agents",
    );
    expect(redirect).toHaveBeenCalledWith("/workspace/agents");
  });

  test("allows admin users to render the admin page", async () => {
    getServerSideUser.mockResolvedValue({
      tag: "authenticated",
      user: {
        id: "admin-1",
        email: "admin@example.com",
        system_role: "admin",
        needs_setup: false,
      },
    });
    const { default: WorkspaceAdminPage } = await loadAdminPage();

    await expect(Promise.resolve(WorkspaceAdminPage())).resolves.toBeTruthy();
    expect(redirect).not.toHaveBeenCalled();
  });
});

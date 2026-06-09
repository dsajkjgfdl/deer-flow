import { describe, expect, test, vi } from "vitest";

const redirect = vi.fn((path: string) => {
  throw new Error(`NEXT_REDIRECT:${path}`);
});
const getServerSideUser = vi.fn();
const authProvider = vi.fn(({ children }: { children: unknown }) => children);
const workspaceContent = vi.fn(
  ({ children }: { children: unknown }) => children,
);

vi.mock("next/navigation", () => ({ redirect }));
vi.mock("@/core/auth/server", () => ({ getServerSideUser }));
vi.mock("@/core/auth/AuthProvider", () => ({ AuthProvider: authProvider }));
vi.mock("@/app/workspace/workspace-content", () => ({
  WorkspaceContent: workspaceContent,
}));

async function loadLayout() {
  vi.resetModules();
  redirect.mockClear();
  authProvider.mockClear();
  workspaceContent.mockClear();
  return await import("@/app/admin/layout");
}

describe("admin layout", () => {
  test("renders admin pages inside the workspace sidebar shell", async () => {
    const user = {
      id: "admin-1",
      email: "admin@example.com",
      system_role: "admin",
      needs_setup: false,
    };
    getServerSideUser.mockResolvedValue({ tag: "authenticated", user });
    const { default: AdminLayout } = await loadLayout();

    const rendered = await Promise.resolve(
      AdminLayout({ children: "content" }),
    );

    expect((rendered as { type?: unknown }).type).toBe(authProvider);
    expect(
      (rendered as { props?: { initialUser?: unknown } }).props?.initialUser,
    ).toBe(user);
    expect(
      (rendered as { props?: { children?: { type?: unknown } } }).props
        ?.children?.type,
    ).toBe(workspaceContent);
    expect(redirect).not.toHaveBeenCalled();
  });

  test("redirects normal users away from the admin shell", async () => {
    getServerSideUser.mockResolvedValue({
      tag: "authenticated",
      user: {
        id: "user-1",
        email: "user@example.com",
        system_role: "user",
        needs_setup: false,
      },
    });
    const { default: AdminLayout } = await loadLayout();

    await expect(
      Promise.resolve(AdminLayout({ children: "content" })),
    ).rejects.toThrow("NEXT_REDIRECT:/workspace/agents");
    expect(redirect).toHaveBeenCalledWith("/workspace/agents");
  });
});

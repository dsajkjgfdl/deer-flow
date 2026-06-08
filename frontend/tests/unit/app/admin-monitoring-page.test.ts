import { describe, expect, test, vi } from "vitest";

const redirect = vi.fn((path: string) => {
  throw new Error(`NEXT_REDIRECT:${path}`);
});

const getServerSideUser = vi.fn();
const queryClientProvider = vi.fn(({ children }: { children: unknown }) => children);

vi.mock("next/navigation", () => ({ redirect }));
vi.mock("@/core/auth/server", () => ({ getServerSideUser }));
vi.mock("@/components/query-client-provider", () => ({
  QueryClientProvider: queryClientProvider,
}));
vi.mock("@/components/platform-admin/monitoring/agent-monitoring-page", () => ({
  AgentMonitoringPage: () => null,
}));

async function loadPage() {
  vi.resetModules();
  redirect.mockClear();
  queryClientProvider.mockClear();
  return await import("@/app/admin/monitoring/page");
}

describe("admin monitoring page route", () => {
  test("redirects normal users away from the standalone admin monitoring page", async () => {
    getServerSideUser.mockResolvedValue({
      tag: "authenticated",
      user: {
        id: "user-1",
        email: "user@example.com",
        system_role: "user",
        needs_setup: false,
      },
    });
    const { default: AdminMonitoringPage } = await loadPage();

    await expect(Promise.resolve(AdminMonitoringPage())).rejects.toThrow(
      "NEXT_REDIRECT:/workspace/agents",
    );
    expect(redirect).toHaveBeenCalledWith("/workspace/agents");
  });

  test("allows admin users to render standalone admin monitoring page", async () => {
    getServerSideUser.mockResolvedValue({
      tag: "authenticated",
      user: {
        id: "admin-1",
        email: "admin@example.com",
        system_role: "admin",
        needs_setup: false,
      },
    });
    const { default: AdminMonitoringPage } = await loadPage();

    const rendered = await Promise.resolve(AdminMonitoringPage());

    expect(rendered).toBeTruthy();
    expect(redirect).not.toHaveBeenCalled();
    expect((rendered as { type?: unknown }).type).toBe(queryClientProvider);
  });
});

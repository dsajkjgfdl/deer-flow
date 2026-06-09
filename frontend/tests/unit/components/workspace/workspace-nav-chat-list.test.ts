import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, test, vi } from "vitest";

const state = vi.hoisted(() => ({
  pathname: "/workspace/chats",
  user: {
    id: "admin-1",
    email: "admin@example.com",
    system_role: "admin",
    needs_setup: false,
  } as {
    id: string;
    email: string;
    system_role: "admin" | "user";
    needs_setup: boolean;
  } | null,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => state.pathname,
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children?: ReactNode;
    href: string;
  }) => createElement("a", { href, ...props }, children),
}));

vi.mock("@/components/ui/sidebar", () => ({
  SidebarGroup: ({ children }: { children?: ReactNode }) =>
    createElement("div", null, children),
  SidebarMenu: ({ children }: { children?: ReactNode }) =>
    createElement("nav", null, children),
  SidebarMenuButton: ({
    children,
    isActive,
  }: {
    children?: ReactNode;
    isActive?: boolean;
  }) => createElement("div", { "data-active": isActive }, children),
  SidebarMenuItem: ({ children }: { children?: ReactNode }) =>
    createElement("div", null, children),
}));

vi.mock("@/core/auth/AuthProvider", () => ({
  useAuth: () => ({ user: state.user }),
}));

vi.mock("@/core/i18n/hooks", () => ({
  useI18n: () => ({
    t: {
      sidebar: {
        agents: "智能体",
        chats: "对话",
        platformAdmin: "管理后台",
        agentMonitoring: "智能体监控",
      },
    },
  }),
}));

async function renderNavigation() {
  const { WorkspaceNavChatList } =
    await import("@/components/workspace/workspace-nav-chat-list");
  return renderToStaticMarkup(createElement(WorkspaceNavChatList));
}

describe("WorkspaceNavChatList", () => {
  beforeEach(() => {
    state.pathname = "/workspace/chats";
    state.user = {
      id: "admin-1",
      email: "admin@example.com",
      system_role: "admin",
      needs_setup: false,
    };
  });

  test("shows an active agent monitoring entry for admins", async () => {
    state.pathname = "/admin/monitoring";

    const markup = await renderNavigation();

    expect(markup).toContain('href="/admin/monitoring"');
    expect(markup).toContain("智能体监控");
    expect(markup).toMatch(
      /data-active="true"><a[^>]+href="\/admin\/monitoring"/,
    );
  });

  test("hides admin entries from normal users", async () => {
    state.user = {
      id: "user-1",
      email: "user@example.com",
      system_role: "user",
      needs_setup: false,
    };

    const markup = await renderNavigation();

    expect(markup).not.toContain("管理后台");
    expect(markup).not.toContain("智能体监控");
    expect(markup).not.toContain('href="/admin/monitoring"');
  });
});

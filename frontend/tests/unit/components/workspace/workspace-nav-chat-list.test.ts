import { beforeEach, describe, expect, rs, test } from "@rstest/core";
import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const state = rs.hoisted(() => ({
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

rs.mock("next/navigation", () => ({
  usePathname: () => state.pathname,
}));

rs.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children?: ReactNode;
    href: string;
  }) => createElement("a", { href, ...props }, children),
}));

rs.mock("@/components/ui/sidebar", () => ({
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

rs.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children?: ReactNode }) =>
    createElement("div", null, children),
  TooltipContent: ({ children }: { children?: ReactNode }) =>
    createElement("div", null, children),
  TooltipTrigger: ({ children }: { children?: ReactNode }) =>
    createElement("div", null, children),
}));

rs.mock("@/core/agents", () => ({
  useAgentsApiEnabled: () => ({ enabled: true }),
}));

rs.mock("@/core/auth/AuthProvider", () => ({
  useAuth: () => ({ user: state.user }),
}));

rs.mock("@/core/i18n/hooks", () => ({
  useI18n: () => ({
    t: {
      sidebar: {
        agents: "智能体",
        chats: "对话",
        scheduledTasks: "定时任务",
        platformAdmin: "管理后台",
        agentMonitoring: "智能体监控",
        agentsDisabledTooltip: "智能体功能未启用",
      },
    },
  }),
}));

async function renderNavigation() {
  rs.resetModules();
  const { WorkspaceNavChatList } = await import(
    "@/components/workspace/workspace-nav-chat-list"
  );
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

  test("shows platform admin and agent monitoring entries for admins", async () => {
    const markup = await renderNavigation();

    expect(markup).toContain('href="/workspace/admin"');
    expect(markup).toContain("管理后台");
    expect(markup).toContain('href="/admin/monitoring"');
    expect(markup).toContain("智能体监控");
  });

  test("marks agent monitoring active on the monitoring route", async () => {
    state.pathname = "/admin/monitoring";

    const markup = await renderNavigation();

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
    expect(markup).not.toContain('href="/workspace/admin"');
    expect(markup).not.toContain('href="/admin/monitoring"');
  });
});

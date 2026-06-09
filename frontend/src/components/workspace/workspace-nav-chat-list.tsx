"use client";

import {
  ActivityIcon,
  BotIcon,
  MessagesSquare,
  ShieldCheckIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { useAuth } from "@/core/auth/AuthProvider";
import { canAccessPlatformAdmin } from "@/core/auth/roles";
import { useI18n } from "@/core/i18n/hooks";

export function WorkspaceNavChatList() {
  const { t } = useI18n();
  const { user } = useAuth();
  const pathname = usePathname();
  const showPlatformAdmin = canAccessPlatformAdmin(user);

  return (
    <SidebarGroup className="pt-1">
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton isActive={pathname === "/workspace/chats"} asChild>
            <Link className="text-muted-foreground" href="/workspace/chats">
              <MessagesSquare />
              <span>{t.sidebar.chats}</span>
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <SidebarMenuItem>
          <SidebarMenuButton
            isActive={pathname.startsWith("/workspace/agents")}
            asChild
          >
            <Link className="text-muted-foreground" href="/workspace/agents">
              <BotIcon />
              <span>{t.sidebar.agents}</span>
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
        {showPlatformAdmin && (
          <>
            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={pathname.startsWith("/workspace/admin")}
                asChild
              >
                <Link className="text-muted-foreground" href="/workspace/admin">
                  <ShieldCheckIcon />
                  <span>{t.sidebar.platformAdmin}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={pathname.startsWith("/admin/monitoring")}
                asChild
              >
                <Link
                  className="text-muted-foreground"
                  href="/admin/monitoring"
                >
                  <ActivityIcon />
                  <span>{t.sidebar.agentMonitoring}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </>
        )}
      </SidebarMenu>
    </SidebarGroup>
  );
}

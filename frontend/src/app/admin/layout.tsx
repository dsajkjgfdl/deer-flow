import { redirect } from "next/navigation";

import { WorkspaceContent } from "@/app/workspace/workspace-content";
import { AuthProvider } from "@/core/auth/AuthProvider";
import { canAccessPlatformAdmin } from "@/core/auth/roles";
import { getServerSideUser } from "@/core/auth/server";

export const dynamic = "force-dynamic";

export default async function AdminLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const result = await getServerSideUser();
  if (result.tag !== "authenticated" || !canAccessPlatformAdmin(result.user)) {
    redirect("/workspace/agents");
  }

  return (
    <AuthProvider initialUser={result.user}>
      <WorkspaceContent>{children}</WorkspaceContent>
    </AuthProvider>
  );
}

import { redirect } from "next/navigation";

import { PlatformAdminPage } from "@/components/workspace/admin/platform-admin-page";
import { canAccessPlatformAdmin } from "@/core/auth/roles";
import { getServerSideUser } from "@/core/auth/server";

export default async function WorkspaceAdminPage() {
  const result = await getServerSideUser();
  if (result.tag !== "authenticated" || !canAccessPlatformAdmin(result.user)) {
    redirect("/workspace/agents");
  }

  return <PlatformAdminPage />;
}

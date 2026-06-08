import { redirect } from "next/navigation";

import { AgentMonitoringPage } from "@/components/platform-admin/monitoring/agent-monitoring-page";
import { QueryClientProvider } from "@/components/query-client-provider";
import { canAccessPlatformAdmin } from "@/core/auth/roles";
import { getServerSideUser } from "@/core/auth/server";

export default async function AdminMonitoringPage() {
  const result = await getServerSideUser();
  if (result.tag !== "authenticated" || !canAccessPlatformAdmin(result.user)) {
    redirect("/workspace/agents");
  }

  return (
    <QueryClientProvider>
      <AgentMonitoringPage />
    </QueryClientProvider>
  );
}

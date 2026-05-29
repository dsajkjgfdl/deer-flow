"use client";

import {
  ActivityIcon,
  ClipboardListIcon,
  KeyRoundIcon,
  LibraryIcon,
} from "lucide-react";
import { useState } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { AgentCatalogPage } from "./agent-catalog-page";
import { AuditPage } from "./audit-page";
import { MonitoringPage } from "./monitoring-page";
import { UserAgentAssignmentPage } from "./user-agent-assignment-page";

type PlatformAdminTab = "catalog" | "assignments" | "monitoring" | "audit";

export function PlatformAdminPage() {
  const [activeTab, setActiveTab] = useState<PlatformAdminTab>("catalog");

  return (
    <div className="flex size-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold">Agent platform</h1>
          <p className="text-muted-foreground mt-0.5 text-sm">
            Catalog, assignments, monitoring, and audit.
          </p>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-6">
        <Tabs
          value={activeTab}
          onValueChange={(value) => setActiveTab(value as PlatformAdminTab)}
          className="gap-5"
        >
          <TabsList
            variant="line"
            className="w-full justify-start overflow-x-auto"
          >
            <TabsTrigger
              value="catalog"
              onClick={() => setActiveTab("catalog")}
            >
              <LibraryIcon className="h-4 w-4" />
              Catalog
            </TabsTrigger>
            <TabsTrigger
              value="assignments"
              onClick={() => setActiveTab("assignments")}
            >
              <KeyRoundIcon className="h-4 w-4" />
              Assignments
            </TabsTrigger>
            <TabsTrigger
              value="monitoring"
              onClick={() => setActiveTab("monitoring")}
            >
              <ActivityIcon className="h-4 w-4" />
              Monitoring
            </TabsTrigger>
            <TabsTrigger value="audit" onClick={() => setActiveTab("audit")}>
              <ClipboardListIcon className="h-4 w-4" />
              Audit
            </TabsTrigger>
          </TabsList>

          <TabsContent value="catalog">
            <AgentCatalogPage />
          </TabsContent>
          <TabsContent value="assignments">
            <UserAgentAssignmentPage />
          </TabsContent>
          <TabsContent value="monitoring">
            <MonitoringPage />
          </TabsContent>
          <TabsContent value="audit">
            <AuditPage />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

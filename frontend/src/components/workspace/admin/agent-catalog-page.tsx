"use client";

import { AlertCircleIcon, BotIcon, SearchIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useAgentCatalog } from "@/core/platform";
import type { AgentCatalogEntry, AgentCatalogStatus } from "@/core/platform";

function statusBadgeVariant(status: AgentCatalogStatus) {
  if (status === "invalid") return "destructive" as const;
  if (status === "warning") return "secondary" as const;
  return "outline" as const;
}

function shortHash(hash: string | null | undefined) {
  return hash ? hash.slice(0, 10) : "-";
}

function listText(values: string[] | null | undefined) {
  return values?.length ? values.join(", ") : "-";
}

function matchesAgent(entry: AgentCatalogEntry, query: string) {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return [
    entry.name,
    entry.display_name ?? "",
    entry.description,
    entry.model ?? "",
    ...(entry.skills ?? []),
    ...(entry.mcp_servers ?? []),
  ]
    .join(" ")
    .toLowerCase()
    .includes(q);
}

export function AgentCatalogPage() {
  const { agents, isLoading, error } = useAgentCatalog();
  const [query, setQuery] = useState("");
  const filteredAgents = useMemo(
    () => agents.filter((agent) => matchesAgent(agent, query)),
    [agents, query],
  );

  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-base font-semibold">Agent catalog</h2>
          <p className="text-muted-foreground mt-1 text-sm">
            File-backed agents scanned from the repository.
          </p>
        </div>
        <div className="relative w-full md:w-72">
          <SearchIcon className="text-muted-foreground pointer-events-none absolute top-2.5 left-2.5 h-4 w-4" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="pl-8"
            placeholder="Search agents"
          />
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertCircleIcon />
          <AlertTitle>Catalog unavailable</AlertTitle>
          <AlertDescription>
            {error instanceof Error ? error.message : String(error)}
          </AlertDescription>
        </Alert>
      )}

      <div className="overflow-x-auto rounded-md border">
        <table className="w-full min-w-[920px] text-sm">
          <thead className="bg-muted/50 text-muted-foreground">
            <tr className="text-left">
              <th className="px-4 py-3 font-medium">Agent</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Model</th>
              <th className="px-4 py-3 font-medium">MCP</th>
              <th className="px-4 py-3 font-medium">Skills</th>
              <th className="px-4 py-3 font-medium">Config hash</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td
                  className="text-muted-foreground px-4 py-8 text-center"
                  colSpan={6}
                >
                  Loading...
                </td>
              </tr>
            ) : filteredAgents.length === 0 ? (
              <tr>
                <td
                  className="text-muted-foreground px-4 py-8 text-center"
                  colSpan={6}
                >
                  No agents found.
                </td>
              </tr>
            ) : (
              filteredAgents.map((agent) => (
                <tr key={agent.name} className="border-t align-top">
                  <td className="px-4 py-3">
                    <div className="flex items-start gap-2">
                      <div className="bg-muted mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md">
                        <BotIcon className="text-muted-foreground h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <div className="font-medium">
                          {agent.display_name ?? agent.name}
                        </div>
                        <div className="text-muted-foreground mt-0.5 truncate text-xs">
                          {agent.name}
                        </div>
                        {agent.description && (
                          <div className="text-muted-foreground mt-1 line-clamp-2 max-w-md text-xs">
                            {agent.description}
                          </div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={statusBadgeVariant(agent.status)}>
                      {agent.status}
                    </Badge>
                    {[...agent.validation_errors, ...agent.validation_warnings]
                      .slice(0, 2)
                      .map((message) => (
                        <div
                          key={message}
                          className="text-muted-foreground mt-1 max-w-52 text-xs"
                        >
                          {message}
                        </div>
                      ))}
                  </td>
                  <td className="px-4 py-3">{agent.model ?? "-"}</td>
                  <td className="text-muted-foreground px-4 py-3 text-xs">
                    {listText(agent.mcp_servers)}
                  </td>
                  <td className="text-muted-foreground px-4 py-3 text-xs">
                    {listText(agent.skills)}
                  </td>
                  <td className="text-muted-foreground px-4 py-3 font-mono text-xs">
                    {shortHash(agent.config_hash)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

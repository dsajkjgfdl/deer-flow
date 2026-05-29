"use client";

import {
  ActivityIcon,
  AlertCircleIcon,
  GaugeIcon,
  WrenchIcon,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { useRunMonitoring, useToolMonitoring } from "@/core/platform";

function displayError(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function numberText(value: number | null | undefined) {
  return value == null ? "-" : new Intl.NumberFormat().format(value);
}

export function MonitoringPage() {
  const runMonitoring = useRunMonitoring();
  const toolMonitoring = useToolMonitoring();
  const monitoringError = runMonitoring.error ?? toolMonitoring.error;

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-base font-semibold">Monitoring</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          Run and tool activity grouped by agent.
        </p>
      </div>

      {monitoringError && (
        <Alert variant="destructive">
          <AlertCircleIcon />
          <AlertTitle>Monitoring unavailable</AlertTitle>
          <AlertDescription>{displayError(monitoringError)}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-md border p-4">
          <div className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
            <ActivityIcon className="h-4 w-4" />
            Runs
          </div>
          <div className="mt-2 text-2xl font-semibold">
            {numberText(
              runMonitoring.items.reduce(
                (sum, item) => sum + item.run_count,
                0,
              ),
            )}
          </div>
        </div>
        <div className="rounded-md border p-4">
          <div className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
            <WrenchIcon className="h-4 w-4" />
            Tool calls
          </div>
          <div className="mt-2 text-2xl font-semibold">
            {numberText(
              toolMonitoring.items.reduce(
                (sum, item) => sum + item.call_count,
                0,
              ),
            )}
          </div>
        </div>
        <div className="rounded-md border p-4">
          <div className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
            <GaugeIcon className="h-4 w-4" />
            Errors
          </div>
          <div className="mt-2 text-2xl font-semibold">
            {numberText(
              runMonitoring.items.reduce(
                (sum, item) => sum + item.error_count,
                0,
              ) +
                toolMonitoring.items.reduce(
                  (sum, item) => sum + item.error_count,
                  0,
                ),
            )}
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="overflow-x-auto rounded-md border">
          <div className="border-b px-4 py-3 text-sm font-medium">
            Runs by agent
          </div>
          <table className="w-full min-w-[640px] text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr className="text-left">
                <th className="px-4 py-3 font-medium">Agent</th>
                <th className="px-4 py-3 font-medium">Runs</th>
                <th className="px-4 py-3 font-medium">Success</th>
                <th className="px-4 py-3 font-medium">Error</th>
                <th className="px-4 py-3 font-medium">Tokens</th>
                <th className="px-4 py-3 font-medium">LLM calls</th>
              </tr>
            </thead>
            <tbody>
              {runMonitoring.isLoading ? (
                <tr>
                  <td
                    className="text-muted-foreground px-4 py-8 text-center"
                    colSpan={6}
                  >
                    Loading...
                  </td>
                </tr>
              ) : runMonitoring.items.length === 0 ? (
                <tr>
                  <td
                    className="text-muted-foreground px-4 py-8 text-center"
                    colSpan={6}
                  >
                    No run data.
                  </td>
                </tr>
              ) : (
                runMonitoring.items.map((item) => (
                  <tr key={item.agent_name} className="border-t">
                    <td className="px-4 py-3 font-medium">{item.agent_name}</td>
                    <td className="px-4 py-3">{numberText(item.run_count)}</td>
                    <td className="px-4 py-3">
                      {numberText(item.success_count)}
                    </td>
                    <td className="px-4 py-3">
                      {numberText(item.error_count)}
                    </td>
                    <td className="px-4 py-3">
                      {numberText(item.total_tokens)}
                    </td>
                    <td className="px-4 py-3">
                      {numberText(item.llm_call_count)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="overflow-x-auto rounded-md border">
          <div className="border-b px-4 py-3 text-sm font-medium">
            Tools by agent
          </div>
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr className="text-left">
                <th className="px-4 py-3 font-medium">Agent</th>
                <th className="px-4 py-3 font-medium">Server</th>
                <th className="px-4 py-3 font-medium">Tool</th>
                <th className="px-4 py-3 font-medium">Calls</th>
                <th className="px-4 py-3 font-medium">Errors</th>
                <th className="px-4 py-3 font-medium">Avg ms</th>
              </tr>
            </thead>
            <tbody>
              {toolMonitoring.isLoading ? (
                <tr>
                  <td
                    className="text-muted-foreground px-4 py-8 text-center"
                    colSpan={6}
                  >
                    Loading...
                  </td>
                </tr>
              ) : toolMonitoring.items.length === 0 ? (
                <tr>
                  <td
                    className="text-muted-foreground px-4 py-8 text-center"
                    colSpan={6}
                  >
                    No tool data.
                  </td>
                </tr>
              ) : (
                toolMonitoring.items.map((item) => (
                  <tr
                    key={`${item.agent_name}:${item.mcp_server_name}:${item.tool_name}`}
                    className="border-t"
                  >
                    <td className="px-4 py-3 font-medium">{item.agent_name}</td>
                    <td className="px-4 py-3">
                      <Badge variant="outline">
                        {item.mcp_server_name ?? "local"}
                      </Badge>
                    </td>
                    <td className="text-muted-foreground px-4 py-3 font-mono text-xs">
                      {item.tool_name}
                    </td>
                    <td className="px-4 py-3">{numberText(item.call_count)}</td>
                    <td className="px-4 py-3">
                      {numberText(item.error_count)}
                    </td>
                    <td className="px-4 py-3">
                      {numberText(item.avg_latency_ms)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="overflow-x-auto rounded-md border">
        <div className="border-b px-4 py-3 text-sm font-medium">
          Recent tool failures
        </div>
        <table className="w-full min-w-[760px] text-sm">
          <thead className="bg-muted/50 text-muted-foreground">
            <tr className="text-left">
              <th className="px-4 py-3 font-medium">Agent</th>
              <th className="px-4 py-3 font-medium">Tool</th>
              <th className="px-4 py-3 font-medium">Run</th>
              <th className="px-4 py-3 font-medium">Error</th>
            </tr>
          </thead>
          <tbody>
            {toolMonitoring.recentFailures.length === 0 ? (
              <tr>
                <td
                  className="text-muted-foreground px-4 py-8 text-center"
                  colSpan={4}
                >
                  No recent failures.
                </td>
              </tr>
            ) : (
              toolMonitoring.recentFailures.map((failure) => (
                <tr
                  key={failure.id ?? `${failure.run_id}:${failure.tool_name}`}
                  className="border-t"
                >
                  <td className="px-4 py-3">{failure.agent_name ?? "-"}</td>
                  <td className="text-muted-foreground px-4 py-3 font-mono text-xs">
                    {failure.tool_name}
                  </td>
                  <td className="text-muted-foreground px-4 py-3 font-mono text-xs">
                    {failure.run_id ?? "-"}
                  </td>
                  <td className="px-4 py-3">{failure.error ?? "-"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

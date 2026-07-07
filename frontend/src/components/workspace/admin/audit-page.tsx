"use client";

import { AlertCircleIcon, ClipboardListIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { useAdminAudit } from "@/core/platform";

function displayError(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function formatDate(value: string | undefined) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function AuditPage() {
  const { items, isLoading, error } = useAdminAudit();

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">Admin audit</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          Assignment changes made through the platform API.
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertCircleIcon />
          <AlertTitle>Audit unavailable</AlertTitle>
          <AlertDescription>{displayError(error)}</AlertDescription>
        </Alert>
      )}

      <div className="overflow-x-auto rounded-md border">
        <table className="w-full min-w-[840px] text-sm">
          <thead className="bg-muted/50 text-muted-foreground">
            <tr className="text-left">
              <th className="px-4 py-3 font-medium">Time</th>
              <th className="px-4 py-3 font-medium">Action</th>
              <th className="px-4 py-3 font-medium">Actor</th>
              <th className="px-4 py-3 font-medium">Target user</th>
              <th className="px-4 py-3 font-medium">Target agent</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td
                  className="text-muted-foreground px-4 py-8 text-center"
                  colSpan={5}
                >
                  Loading...
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td className="px-4 py-10 text-center" colSpan={5}>
                  <div className="text-muted-foreground flex flex-col items-center gap-2 text-sm">
                    <ClipboardListIcon className="h-5 w-5" />
                    No audit records.
                  </div>
                </td>
              </tr>
            ) : (
              items.map((item, index) => (
                <tr key={item.id ?? index} className="border-t">
                  <td className="text-muted-foreground px-4 py-3 text-xs">
                    {formatDate(item.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant="outline">{item.action}</Badge>
                  </td>
                  <td className="text-muted-foreground px-4 py-3 font-mono text-xs">
                    {item.actor_user_id}
                  </td>
                  <td className="text-muted-foreground px-4 py-3 font-mono text-xs">
                    {item.target_user_id ?? "-"}
                  </td>
                  <td className="px-4 py-3">{item.target_agent_name ?? "-"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

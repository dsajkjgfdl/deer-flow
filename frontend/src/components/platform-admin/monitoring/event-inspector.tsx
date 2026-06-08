"use client";

import {
  ClockIcon,
  CodeIcon,
  EyeIcon,
  TimerIcon,
  WrenchIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { MonitoringTimelineEvent } from "@/core/platform";

import {
  durationText,
  jsonText,
  statusVariant,
  timeText,
} from "./format";

interface EventInspectorProps {
  event: MonitoringTimelineEvent | null;
}

function Field({
  label,
  value,
}: {
  label: string;
  value: string | number | null | undefined;
}) {
  return (
    <div className="min-w-0">
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="mt-1 truncate text-xs">{value ?? "-"}</div>
    </div>
  );
}

export function EventInspector({ event }: EventInspectorProps) {
  return (
    <section className="min-h-0">
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <EyeIcon className="text-muted-foreground size-4 shrink-0" />
            <h2 className="truncate text-sm font-semibold">Event inspector</h2>
          </div>
          {event?.status && (
            <Badge variant={statusVariant(event.status)}>{event.status}</Badge>
          )}
        </div>

        {!event ? (
          <div className="text-muted-foreground px-4 py-8 text-center text-sm">
            No event selected.
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="grid gap-3 border-b px-4 py-3 sm:grid-cols-2 xl:grid-cols-4">
              <Field label="Occurred" value={timeText(event.occurred_at)} />
              <Field label="Beijing" value={event.occurred_at_bj} />
              <Field label="Source" value={event.source} />
              <Field label="Kind" value={event.kind} />
              <Field label="Tool" value={event.tool_name} />
              <Field label="MCP" value={event.mcp_server_name} />
              <Field
                label="Duration"
                value={durationText(event.duration_ms)}
              />
              <Field label="Seq" value={event.seq ?? "-"} />
            </div>

            <div className="grid gap-0 xl:grid-cols-2">
              <div className="min-w-0 border-b px-4 py-3 xl:border-r xl:border-b-0">
                <div className="text-muted-foreground mb-2 flex items-center gap-2 text-xs font-medium">
                  <CodeIcon className="size-3.5" />
                  Content
                </div>
                <pre className="bg-muted/40 max-h-[360px] overflow-auto rounded-md border p-3 text-xs whitespace-pre-wrap">
                  {jsonText(event.content)}
                </pre>
              </div>
              <div className="min-w-0 px-4 py-3">
                <div className="text-muted-foreground mb-2 flex items-center gap-2 text-xs font-medium">
                  <WrenchIcon className="size-3.5" />
                  Metadata
                </div>
                <pre className="bg-muted/40 max-h-[360px] overflow-auto rounded-md border p-3 text-xs whitespace-pre-wrap">
                  {jsonText(event.metadata)}
                </pre>
              </div>
            </div>

            <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-2 border-t px-4 py-3 text-xs">
              <span className="flex items-center gap-1.5">
                <ClockIcon className="size-3.5" />
                {event.occurred_at_bj ?? timeText(event.occurred_at)}
              </span>
              <span className="flex items-center gap-1.5">
                <TimerIcon className="size-3.5" />
                {durationText(event.duration_ms)}
              </span>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

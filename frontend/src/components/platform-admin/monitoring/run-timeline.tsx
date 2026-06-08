"use client";

import {
  ActivityIcon,
  ClockIcon,
  TimerIcon,
  WrenchIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { MonitoringRunTimeline } from "@/core/platform";
import { cn } from "@/lib/utils";

import {
  durationText,
  eventKey,
  eventTone,
  shortId,
  statusVariant,
  timeText,
} from "./format";

interface RunTimelineProps {
  timeline: MonitoringRunTimeline | null;
  selectedEventKey: string | null;
  onSelectEventKey: (key: string) => void;
  isLoading: boolean;
  isImported: boolean;
}

function eventTitle(title: string | null | undefined, kind: string): string {
  const text = title?.trim();
  if (!text) return kind;
  return text;
}

export function RunTimeline({
  timeline,
  selectedEventKey,
  onSelectEventKey,
  isLoading,
  isImported,
}: RunTimelineProps) {
  const events = timeline?.events ?? [];

  return (
    <section className="min-h-0 border-b">
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <ActivityIcon className="text-muted-foreground size-4 shrink-0" />
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold">Run timeline</h2>
              <div className="text-muted-foreground truncate font-mono text-xs">
                {timeline ? shortId(timeline.run.run_id) : "-"}
              </div>
            </div>
          </div>
          {isImported && <Badge variant="secondary">Imported</Badge>}
        </div>

        <div className="min-h-[280px] flex-1 overflow-y-auto px-3 py-3">
          {isLoading ? (
            <div className="text-muted-foreground px-4 py-8 text-center text-sm">
              Loading...
            </div>
          ) : !timeline || events.length === 0 ? (
            <div className="text-muted-foreground px-4 py-8 text-center text-sm">
              No timeline events.
            </div>
          ) : (
            <div className="space-y-2">
              {events.map((event, index) => {
                const rowKey = eventKey(event, index);
                const isSelected = selectedEventKey === rowKey;
                const title = eventTitle(event.title, event.kind);
                const toolLabel =
                  event.tool_name || event.mcp_server_name
                    ? [event.mcp_server_name, event.tool_name]
                        .filter(Boolean)
                        .join("/")
                    : null;

                return (
                  <button
                    key={`${index}:${event.seq ?? "none"}:${event.kind}:${event.occurred_at ?? ""}`}
                    type="button"
                    className={cn(
                      "flex w-full gap-3 rounded-md border px-3 py-2 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      eventTone(event),
                      isSelected && "ring-2 ring-ring",
                    )}
                    onClick={() => onSelectEventKey(rowKey)}
                  >
                    <div className="mt-1 flex flex-col items-center">
                      <div className="bg-background flex size-6 items-center justify-center rounded-full border">
                        {event.source === "tool_audit" ? (
                          <WrenchIcon className="size-3.5 text-blue-600" />
                        ) : (
                          <ActivityIcon className="text-muted-foreground size-3.5" />
                        )}
                      </div>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex min-w-0 items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium">
                            {title}
                          </div>
                          <div className="text-muted-foreground mt-0.5 truncate text-xs">
                            {event.kind}
                          </div>
                        </div>
                        {event.status && (
                          <Badge variant={statusVariant(event.status)}>
                            {event.status}
                          </Badge>
                        )}
                      </div>

                      <div className="text-muted-foreground mt-2 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                        <span className="flex items-center gap-1.5">
                          <ClockIcon className="size-3.5" />
                          {event.occurred_at_bj ?? timeText(event.occurred_at)}
                        </span>
                        {toolLabel && (
                          <span className="flex min-w-0 items-center gap-1.5">
                            <WrenchIcon className="size-3.5" />
                            <span className="truncate">{toolLabel}</span>
                          </span>
                        )}
                        {event.duration_ms != null && (
                          <span className="flex items-center gap-1.5">
                            <TimerIcon className="size-3.5" />
                            {durationText(event.duration_ms)}
                          </span>
                        )}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

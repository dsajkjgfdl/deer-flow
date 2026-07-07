"use client";

import { DownloadIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { exportRunTimelineAsJSON } from "@/core/platform";
import type {
  MonitoringIdentity,
  MonitoringRunTimeline,
  MonitoringTimelineEvent,
} from "@/core/platform";

import { EventInspector } from "./event-inspector";
import { identityText, statusVariant } from "./format";
import { RunTimeline } from "./run-timeline";

interface RunInspectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  runId: string | null;
  identity: MonitoringIdentity | null;
  timeline: MonitoringRunTimeline | null;
  selectedEventKey: string | null;
  onSelectEventKey: (key: string) => void;
  selectedEvent: MonitoringTimelineEvent | null;
  isLoading: boolean;
  isImported: boolean;
}

export function RunInspectionDialog({
  open,
  onOpenChange,
  runId,
  identity,
  timeline,
  selectedEventKey,
  onSelectEventKey,
  selectedEvent,
  isLoading,
  isImported,
}: RunInspectionDialogProps) {
  const displayedRunId = timeline?.run.run_id ?? runId;
  const displayedIdentity = timeline?.identity ?? identity;
  const finalResponse = timeline?.run.last_ai_message?.trim();
  const finalResponseText = finalResponse?.length
    ? finalResponse
    : isLoading
      ? "Loading final response..."
      : "No final response recorded.";

  function handleExportJSON() {
    if (!timeline) return;
    exportRunTimelineAsJSON(timeline);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="grid h-[calc(100vh-2rem)] max-h-[calc(100vh-2rem)] w-[calc(100vw-2rem)] max-w-[calc(100vw-2rem)] grid-rows-[auto_minmax(0,1fr)] gap-0 overflow-hidden p-0 sm:max-w-[calc(100vw-2rem)]">
        <DialogHeader className="border-b px-5 py-4 pr-14 text-left">
          <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <DialogTitle>Run inspection</DialogTitle>
              {timeline?.run.status && (
                <Badge variant={statusVariant(timeline.run.status)}>
                  {timeline.run.status}
                </Badge>
              )}
              {isImported && <Badge variant="secondary">Imported</Badge>}
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={!timeline}
              onClick={handleExportJSON}
            >
              <DownloadIcon className="size-4" />
              Export JSON
            </Button>
          </div>
          <DialogDescription className="flex min-w-0 flex-wrap gap-x-4 gap-y-1">
            <span className="font-mono break-all">
              {displayedRunId ?? "No run selected"}
            </span>
            <span className="truncate">
              {displayedIdentity ? identityText(displayedIdentity) : "-"}
            </span>
          </DialogDescription>
          <div className="bg-muted/30 mt-1 min-w-0 rounded-md border px-3 py-2">
            <div className="text-muted-foreground text-xs font-medium">
              Final response
            </div>
            <div className="mt-1 max-h-28 overflow-y-auto text-sm whitespace-pre-wrap">
              {finalResponseText}
            </div>
          </div>
        </DialogHeader>

        <div className="grid min-h-0 grid-rows-[minmax(280px,42vh)_minmax(360px,1fr)] overflow-y-auto lg:grid-cols-[minmax(320px,0.85fr)_minmax(0,1.5fr)] lg:grid-rows-1 lg:overflow-hidden">
          <RunTimeline
            timeline={timeline}
            runId={runId}
            identity={identity}
            selectedEventKey={selectedEventKey}
            onSelectEventKey={onSelectEventKey}
            isLoading={isLoading}
            isImported={isImported}
          />
          <EventInspector event={selectedEvent} />
        </div>
      </DialogContent>
    </Dialog>
  );
}

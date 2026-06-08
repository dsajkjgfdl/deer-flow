"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  AlertCircleIcon,
  RefreshCwIcon,
  SearchIcon,
  UploadIcon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useMonitoringConversation,
  useMonitoringConversations,
  useMonitoringRunTimeline,
  type MonitoringRunTimeline,
  type MonitoringTimelineEvent,
} from "@/core/platform";

import { ConversationDetail } from "./conversation-detail";
import { ConversationList } from "./conversation-list";
import { EventInspector } from "./event-inspector";
import { ImportRunDialog } from "./import-run-dialog";
import { RunTimeline } from "./run-timeline";

const SOURCE_OPTIONS = [
  "all",
  "web",
  "feishu",
  "dingtalk",
  "wecom",
  "wechat",
  "slack",
  "telegram",
  "discord",
] as const;

const STATUS_OPTIONS = [
  "all",
  "running",
  "success",
  "error",
  "timeout",
  "interrupted",
] as const;

const EMPTY_EVENTS: MonitoringTimelineEvent[] = [];

function displayError(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function eventKey(event: MonitoringTimelineEvent, index: number): string {
  if (typeof event.seq === "number") return `seq:${event.seq}`;
  return `idx:${index}:${event.kind}:${event.occurred_at ?? ""}`;
}

function eventSelectionValue(
  event: MonitoringTimelineEvent,
  index: number,
): number {
  return event.seq ?? index;
}

function selectedSeqFromKey(
  events: MonitoringTimelineEvent[],
  selectedEventKey: string | null,
): number | null {
  if (!selectedEventKey) return null;
  const index = events.findIndex(
    (event, eventIndex) => eventKey(event, eventIndex) === selectedEventKey,
  );
  if (index < 0) return null;
  const event = events[index];
  return event ? eventSelectionValue(event, index) : null;
}

export function AgentMonitoringPage() {
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState({
    limit: 50,
    offset: 0,
    q: "",
    source: "",
    status: "",
    agent_name: "",
  });
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedEventKey, setSelectedEventKey] = useState<string | null>(null);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [importedTimeline, setImportedTimeline] =
    useState<MonitoringRunTimeline | null>(null);

  const conversations = useMonitoringConversations(filters);
  const liveThreadId = importedTimeline ? null : selectedThreadId;
  const liveRunId = importedTimeline ? null : selectedRunId;
  const conversationDetail = useMonitoringConversation(liveThreadId);
  const liveTimeline = useMonitoringRunTimeline(liveRunId);
  const activeTimeline = importedTimeline ?? liveTimeline.timeline;
  const events = activeTimeline?.events ?? EMPTY_EVENTS;
  const selectedSeq = selectedSeqFromKey(events, selectedEventKey);
  const selectedEvent = useMemo(() => {
    if (!selectedEventKey) return null;
    return (
      events.find(
        (event, index) => eventKey(event, index) === selectedEventKey,
      ) ?? null
    );
  }, [events, selectedEventKey]);
  const liveError =
    conversations.error ?? conversationDetail.error ?? liveTimeline.error;

  useEffect(() => {
    if (importedTimeline || selectedThreadId || conversations.page.items.length === 0) {
      return;
    }

    const first = conversations.page.items[0];
    if (!first) return;

    setSelectedThreadId(first.thread_id);
    setSelectedRunId(first.latest_run_id ?? first.run_id ?? null);
    setSelectedEventKey(null);
  }, [conversations.page.items, importedTimeline, selectedThreadId]);

  useEffect(() => {
    if (importedTimeline || selectedRunId || !conversationDetail.conversation) {
      return;
    }

    const firstRun = conversationDetail.conversation.runs[0];
    if (firstRun) {
      setSelectedRunId(firstRun.run_id);
    }
  }, [conversationDetail.conversation, importedTimeline, selectedRunId]);

  useEffect(() => {
    if (events.length === 0) {
      if (selectedEventKey !== null) {
        setSelectedEventKey(null);
      }
      return;
    }

    const exists = selectedEventKey
      ? events.some((event, index) => eventKey(event, index) === selectedEventKey)
      : false;
    if (!exists) {
      const firstEvent = events[0];
      setSelectedEventKey(firstEvent ? eventKey(firstEvent, 0) : null);
    }
  }, [events, selectedEventKey]);

  function handleSelectThread(threadId: string, latestRunId: string | null) {
    setImportedTimeline(null);
    setSelectedThreadId(threadId);
    setSelectedRunId(latestRunId);
    setSelectedEventKey(null);
  }

  function handleSelectRun(runId: string) {
    setImportedTimeline(null);
    setSelectedRunId(runId);
    setSelectedEventKey(null);
  }

  function handleImported(timeline: MonitoringRunTimeline) {
    setImportedTimeline(timeline);
    setSelectedThreadId(null);
    setSelectedRunId(timeline.run.run_id);
    setSelectedEventKey(
      timeline.events[0] ? eventKey(timeline.events[0], 0) : null,
    );
  }

  function handleSelectSeq(seq: number | null) {
    if (seq == null) {
      setSelectedEventKey(null);
      return;
    }

    const index = events.findIndex(
      (event, eventIndex) => eventSelectionValue(event, eventIndex) === seq,
    );
    const event = index >= 0 ? events[index] : undefined;
    setSelectedEventKey(event ? eventKey(event, index) : null);
  }

  function handleRefresh() {
    void queryClient.invalidateQueries({
      queryKey: ["platform", "admin", "monitoring"],
    });
  }

  return (
    <main className="bg-background flex h-screen min-h-0 flex-col">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3">
        <div className="min-w-0">
          <h1 className="truncate text-base font-semibold">Agent monitoring</h1>
          <div className="text-muted-foreground mt-0.5 text-xs">
            {conversations.page.total} conversations
          </div>
        </div>

        <div className="flex min-w-0 flex-1 flex-wrap items-center justify-end gap-2">
          <div className="relative min-w-[220px] flex-1 sm:max-w-xs">
            <SearchIcon className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
            <Input
              className="pl-9"
              placeholder="Search"
              value={filters.q}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  q: event.target.value,
                  offset: 0,
                }))
              }
            />
          </div>

          <Select
            value={filters.source || "all"}
            onValueChange={(value) =>
              setFilters((current) => ({
                ...current,
                source: value === "all" ? "" : value,
                offset: 0,
              }))
            }
          >
            <SelectTrigger className="w-[136px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SOURCE_OPTIONS.map((source) => (
                <SelectItem key={source} value={source}>
                  {source === "all" ? "All sources" : source}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={filters.status || "all"}
            onValueChange={(value) =>
              setFilters((current) => ({
                ...current,
                status: value === "all" ? "" : value,
                offset: 0,
              }))
            }
          >
            <SelectTrigger className="w-[136px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((status) => (
                <SelectItem key={status} value={status}>
                  {status === "all" ? "All status" : status}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button type="button" variant="outline" onClick={handleRefresh}>
            <RefreshCwIcon className="size-4" />
            Refresh
          </Button>
          <Button type="button" onClick={() => setImportDialogOpen(true)}>
            <UploadIcon className="size-4" />
            Import
          </Button>
        </div>

        {liveError && (
          <Alert className="w-full py-2" variant="destructive">
            <AlertCircleIcon />
            <AlertTitle>Monitoring unavailable</AlertTitle>
            <AlertDescription>{displayError(liveError)}</AlertDescription>
          </Alert>
        )}
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[360px_minmax(360px,1fr)_minmax(420px,1.2fr)]">
        <ConversationList
          items={conversations.page.items}
          selectedThreadId={selectedThreadId}
          isLoading={conversations.isLoading}
          onSelectThread={handleSelectThread}
        />
        <ConversationDetail
          conversation={importedTimeline ? null : conversationDetail.conversation}
          selectedRunId={selectedRunId}
          isLoading={importedTimeline ? false : conversationDetail.isLoading}
          onSelectRun={handleSelectRun}
        />
        <div className="grid min-h-0 grid-rows-[minmax(0,1fr)_minmax(220px,34vh)]">
          <RunTimeline
            timeline={activeTimeline}
            selectedSeq={selectedSeq}
            onSelectSeq={handleSelectSeq}
            isLoading={importedTimeline ? false : liveTimeline.isLoading}
            isImported={Boolean(importedTimeline)}
          />
          <EventInspector event={selectedEvent} />
        </div>
      </div>

      <ImportRunDialog
        open={importDialogOpen}
        onOpenChange={setImportDialogOpen}
        onImported={handleImported}
      />
    </main>
  );
}

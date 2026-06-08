"use client";

import {
  AlertCircleIcon,
  ClockIcon,
  MessageSquareIcon,
  UserIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { MonitoringConversationItem } from "@/core/platform";
import { cn } from "@/lib/utils";

import { identityText, shortId, statusVariant, timeText } from "./format";

interface ConversationListProps {
  items: MonitoringConversationItem[];
  selectedThreadId: string | null;
  isLoading: boolean;
  onSelectThread: (threadId: string, latestRunId: string | null) => void;
}

function sourceText(item: MonitoringConversationItem): string {
  const source = item.identity.identity_source?.trim();
  if (source) return source;
  return item.identity.identity_type;
}

function previewText(item: MonitoringConversationItem): string {
  const lastMessage = item.last_message?.trim();
  if (lastMessage) return lastMessage;
  const messagePreview = item.message_preview?.trim();
  if (messagePreview) return messagePreview;
  return "-";
}

function errorText(item: MonitoringConversationItem): string | null {
  const errorSummary = item.error_summary?.trim();
  if (errorSummary) return errorSummary;
  const error = item.error?.trim();
  if (!error) return null;
  return error;
}

export function ConversationList({
  items,
  selectedThreadId,
  isLoading,
  onSelectThread,
}: ConversationListProps) {
  return (
    <section className="border-b lg:min-h-0 lg:border-r lg:border-b-0">
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <MessageSquareIcon className="text-muted-foreground size-4 shrink-0" />
            <h2 className="truncate text-sm font-semibold">Recent conversations</h2>
          </div>
          <Badge variant="outline">{items.length}</Badge>
        </div>

        <div className="min-h-[260px] flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="text-muted-foreground px-4 py-8 text-center text-sm">
              Loading...
            </div>
          ) : items.length === 0 ? (
            <div className="text-muted-foreground px-4 py-8 text-center text-sm">
              No conversations.
            </div>
          ) : (
            <div className="divide-y">
              {items.map((item) => {
                const latestRunId = item.latest_run_id ?? item.run_id ?? null;
                const itemError = errorText(item);
                const isSelected = item.thread_id === selectedThreadId;

                return (
                  <button
                    key={item.thread_id}
                    type="button"
                    className={cn(
                      "hover:bg-muted/50 flex w-full flex-col gap-2 px-4 py-3 text-left transition-colors focus-visible:bg-muted focus-visible:outline-none",
                      isSelected && "bg-muted/70",
                    )}
                    onClick={() => onSelectThread(item.thread_id, latestRunId)}
                  >
                    <div className="flex min-w-0 items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex min-w-0 items-center gap-1.5">
                          <UserIcon className="text-muted-foreground size-3.5 shrink-0" />
                          <span className="truncate text-sm font-medium">
                            {identityText(item.identity)}
                          </span>
                        </div>
                        <div className="text-muted-foreground mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                          <span className="font-mono">
                            t:{shortId(item.thread_id)}
                          </span>
                          <span className="font-mono">
                            r:{shortId(latestRunId)}
                          </span>
                          <span>{item.agent_name ?? "-"}</span>
                        </div>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1">
                        <Badge variant={statusVariant(item.status)}>
                          {item.status ?? "unknown"}
                        </Badge>
                        <Badge variant="outline">{sourceText(item)}</Badge>
                      </div>
                    </div>

                    <p className="text-muted-foreground line-clamp-2 break-words text-xs">
                      {previewText(item)}
                    </p>

                    <div className="text-muted-foreground flex min-w-0 items-center justify-between gap-2 text-xs">
                      <span className="flex min-w-0 items-center gap-1.5">
                        <ClockIcon className="size-3.5 shrink-0" />
                        <span className="truncate">
                          {item.updated_at_bj ?? timeText(item.updated_at)}
                        </span>
                      </span>
                      {item.message_count != null && (
                        <span>{item.message_count} messages</span>
                      )}
                    </div>

                    {itemError && (
                      <div className="text-destructive flex min-w-0 items-center gap-1.5 text-xs">
                        <AlertCircleIcon className="size-3.5 shrink-0" />
                        <span className="truncate">{itemError}</span>
                      </div>
                    )}
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

"use client";

import {
  AlertCircleIcon,
  BotIcon,
  ClockIcon,
  GaugeIcon,
  MessageSquareIcon,
  UserIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type {
  MonitoringConversationDetail,
  MonitoringRunItem,
} from "@/core/platform";
import { cn } from "@/lib/utils";

import {
  identityText,
  numberText,
  shortId,
  statusVariant,
  timeText,
} from "./format";

interface ConversationDetailProps {
  conversation: MonitoringConversationDetail | null;
  selectedRunId: string | null;
  isLoading: boolean;
  onSelectRun: (runId: string) => void;
}

function displayText(value?: string | null): string {
  const text = value?.trim();
  if (!text) return "-";
  return text;
}

function isInternalPromptText(value: string): boolean {
  const normalized = value.toLowerCase();
  return (
    normalized.includes("<role>") ||
    normalized.includes("<primary_objective>") ||
    normalized.includes("context extraction assistant") ||
    normalized.includes("your sole objective")
  );
}

function runQuestionText(run: MonitoringRunItem): string | null {
  const candidates = [
    run.first_human_message,
    run.message_preview,
    run.last_message,
  ];

  for (const candidate of candidates) {
    const text = candidate?.trim();
    if (text && !isInternalPromptText(text)) {
      return text;
    }
  }

  return null;
}

function runErrorText(
  errorSummary?: string | null,
  error?: string | null,
): string | null {
  const summary = errorSummary?.trim();
  if (summary) return summary;
  const text = error?.trim();
  if (!text) return null;
  return text;
}

export function ConversationDetail({
  conversation,
  selectedRunId,
  isLoading,
  onSelectRun,
}: ConversationDetailProps) {
  if (isLoading) {
    return (
      <section className="border-b lg:min-h-0 lg:border-r lg:border-b-0">
        <div className="text-muted-foreground px-4 py-8 text-center text-sm">
          Loading...
        </div>
      </section>
    );
  }

  if (!conversation) {
    return (
      <section className="border-b lg:min-h-0 lg:border-r lg:border-b-0">
        <div className="text-muted-foreground px-4 py-8 text-center text-sm">
          No conversation selected.
        </div>
      </section>
    );
  }

  return (
    <section className="border-b lg:min-h-0 lg:border-r lg:border-b-0">
      <div className="flex h-full min-h-0 flex-col">
        <div className="space-y-3 border-b px-4 py-3">
          <div className="flex min-w-0 items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex min-w-0 items-center gap-2">
                <UserIcon className="text-muted-foreground size-4 shrink-0" />
                <h2 className="truncate text-sm font-semibold">
                  {identityText(conversation.identity)}
                </h2>
              </div>
              <div className="text-muted-foreground mt-1 font-mono text-xs">
                t:{shortId(conversation.thread_id)}
              </div>
            </div>
            <Badge variant="outline">{conversation.runs.length} runs</Badge>
          </div>
          <p className="text-muted-foreground line-clamp-3 text-xs break-words">
            {displayText(conversation.message_preview)}
          </p>
        </div>

        <div className="min-h-[300px] flex-1 overflow-y-auto">
          {conversation.runs.length === 0 ? (
            <div className="text-muted-foreground px-4 py-8 text-center text-sm">
              No runs.
            </div>
          ) : (
            <div className="divide-y">
              {conversation.runs.map((run) => {
                const runError = runErrorText(run.error_summary, run.error);
                const isSelected = run.run_id === selectedRunId;
                const question = runQuestionText(run);

                return (
                  <button
                    key={run.run_id}
                    type="button"
                    className={cn(
                      "hover:bg-muted/50 focus-visible:bg-muted flex w-full flex-col gap-2 px-4 py-3 text-left transition-colors focus-visible:outline-none",
                      isSelected && "bg-muted/70",
                    )}
                    onClick={() => onSelectRun(run.run_id)}
                  >
                    <div className="flex min-w-0 items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex min-w-0 items-center gap-1.5">
                          <BotIcon className="text-muted-foreground size-3.5 shrink-0" />
                          <span className="truncate font-mono text-xs font-medium">
                            {run.run_id}
                          </span>
                        </div>
                        <div className="text-muted-foreground mt-1 flex min-w-0 items-center gap-1.5 text-xs">
                          <ClockIcon className="size-3.5 shrink-0" />
                          <span className="truncate">
                            {run.created_at_bj ?? timeText(run.created_at)}
                          </span>
                        </div>
                      </div>
                      <Badge variant={statusVariant(run.status)}>
                        {run.status}
                      </Badge>
                    </div>

                    <div className="bg-muted/30 rounded-md border px-3 py-2">
                      <div className="text-muted-foreground mb-1 text-xs font-medium">
                        Question
                      </div>
                      <div
                        className={cn(
                          "line-clamp-2 text-xs break-words",
                          !question && "text-muted-foreground",
                        )}
                        title={question ?? undefined}
                      >
                        {question ?? "Question unavailable"}
                      </div>
                    </div>

                    <div className="text-muted-foreground grid gap-1 text-xs sm:grid-cols-3">
                      <span className="flex items-center gap-1.5">
                        <GaugeIcon className="size-3.5" />
                        {numberText(run.total_tokens)} tokens
                      </span>
                      <span>{numberText(run.llm_call_count)} LLM</span>
                      <span>
                        <MessageSquareIcon className="mr-1 inline size-3.5" />
                        {numberText(run.message_count)}
                      </span>
                    </div>

                    {runError && (
                      <div className="text-destructive flex min-w-0 items-center gap-1.5 text-xs">
                        <AlertCircleIcon className="size-3.5 shrink-0" />
                        <span className="truncate">{runError}</span>
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

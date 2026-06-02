"use client";

import {
  AlertCircleIcon,
  BotIcon,
  ClockIcon,
  EyeIcon,
  MailIcon,
  MessageSquareIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
  UserIcon,
} from "lucide-react";
import { useMemo, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  useFeedbackConversation,
  useFeedbackSummary,
  useRecentFeedback,
  type FeedbackConversationMessage,
  type FeedbackRecord,
} from "@/core/platform";

function displayError(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function numberText(value: number | null | undefined) {
  return value == null ? "-" : new Intl.NumberFormat().format(value);
}

function percentText(value: number | null | undefined) {
  if (value == null) {
    return "-";
  }
  return `${Math.round(value * 100)}%`;
}

function shortId(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  return value.length > 8 ? value.slice(0, 8) : value;
}

function timeText(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function snippetText(value: string | null | undefined) {
  const text = value?.trim();
  if (text) {
    return text;
  }
  return "-";
}

function extractMessageText(value: unknown): string {
  if (value == null) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map(extractMessageText).filter(Boolean).join("\n");
  }
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const nested =
      obj.content ?? obj.text ?? obj.message ?? obj.output ?? obj.value;
    if (nested !== undefined) {
      return extractMessageText(nested);
    }
    return JSON.stringify(value, null, 2);
  }
  return "";
}

function messageRole(message: FeedbackConversationMessage) {
  const content = message.content;
  const typeValue =
    typeof content === "object" && content !== null
      ? (content as Record<string, unknown>).type
      : undefined;
  const type = typeof typeValue === "string" ? typeValue : "";
  const eventType = message.event_type.toLowerCase();
  if (type.includes("human") || eventType.includes("human")) {
    return "User";
  }
  if (type.includes("ai") || eventType.includes("ai")) {
    return "Assistant";
  }
  if (type.includes("tool") || eventType.includes("tool")) {
    return "Tool";
  }
  return message.event_type;
}

function channelText(item: FeedbackRecord) {
  const channel = item.source_channel?.trim();
  if (channel) {
    return channel;
  }
  return "web";
}

function voterText(item: FeedbackRecord) {
  if (item.source_channel && item.source_channel !== "web") {
    return item.platform_user_id ?? item.user_id ?? "Unknown user";
  }
  return item.user_email ?? item.user_id ?? "Unknown user";
}

export function FeedbackPage() {
  const [selectedFeedbackId, setSelectedFeedbackId] = useState<string | null>(
    null,
  );
  const feedbackSummary = useFeedbackSummary();
  const recentFeedback = useRecentFeedback(20);
  const selectedFeedback = recentFeedback.items.find(
    (item) => item.feedback_id === selectedFeedbackId,
  );
  const feedbackConversation = useFeedbackConversation(selectedFeedbackId);
  const feedbackError = feedbackSummary.error ?? recentFeedback.error;
  const conversationError = feedbackConversation.error;
  const summary = feedbackSummary.summary;
  const negativeItems = useMemo(
    () => recentFeedback.items.filter((item) => item.rating === -1),
    [recentFeedback.items],
  );
  const drawerFeedback =
    feedbackConversation.conversation?.feedback ?? selectedFeedback ?? null;

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-base font-semibold">Feedback</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          User ratings and recent negative feedback by agent.
        </p>
      </div>

      {feedbackError && (
        <Alert variant="destructive">
          <AlertCircleIcon />
          <AlertTitle>Feedback unavailable</AlertTitle>
          <AlertDescription>{displayError(feedbackError)}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-3 md:grid-cols-4">
        <div className="rounded-md border p-4">
          <div className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
            <MessageSquareIcon className="h-4 w-4" />
            Total
          </div>
          <div className="mt-2 text-2xl font-semibold">
            {numberText(summary.total)}
          </div>
        </div>
        <div className="rounded-md border p-4">
          <div className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
            <ThumbsUpIcon className="h-4 w-4" />
            Positive
          </div>
          <div className="mt-2 text-2xl font-semibold">
            {numberText(summary.positive)}
          </div>
        </div>
        <div className="rounded-md border p-4">
          <div className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
            <ThumbsDownIcon className="h-4 w-4" />
            Negative
          </div>
          <div className="mt-2 text-2xl font-semibold">
            {numberText(summary.negative)}
          </div>
        </div>
        <div className="rounded-md border p-4">
          <div className="text-muted-foreground text-xs font-medium">
            Positive rate
          </div>
          <div className="mt-2 text-2xl font-semibold">
            {percentText(summary.positive_rate)}
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="overflow-x-auto rounded-md border">
          <div className="border-b px-4 py-3 text-sm font-medium">
            Feedback by agent
          </div>
          <table className="w-full min-w-[560px] text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr className="text-left">
                <th className="px-4 py-3 font-medium">Agent</th>
                <th className="px-4 py-3 font-medium">Total</th>
                <th className="px-4 py-3 font-medium">Positive</th>
                <th className="px-4 py-3 font-medium">Negative</th>
                <th className="px-4 py-3 font-medium">Rate</th>
              </tr>
            </thead>
            <tbody>
              {feedbackSummary.isLoading ? (
                <tr>
                  <td
                    className="text-muted-foreground px-4 py-8 text-center"
                    colSpan={5}
                  >
                    Loading...
                  </td>
                </tr>
              ) : summary.by_agent.length === 0 ? (
                <tr>
                  <td
                    className="text-muted-foreground px-4 py-8 text-center"
                    colSpan={5}
                  >
                    No feedback data.
                  </td>
                </tr>
              ) : (
                summary.by_agent.map((item) => (
                  <tr key={item.agent_name} className="border-t">
                    <td className="px-4 py-3 font-medium">{item.agent_name}</td>
                    <td className="px-4 py-3">{numberText(item.total)}</td>
                    <td className="px-4 py-3">{numberText(item.positive)}</td>
                    <td className="px-4 py-3">{numberText(item.negative)}</td>
                    <td className="px-4 py-3">
                      {percentText(item.positive_rate)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="rounded-md border">
          <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
            <div className="text-sm font-medium">Recent negative feedback</div>
            <div className="text-muted-foreground text-xs">
              {negativeItems.length} items
            </div>
          </div>
          {recentFeedback.isLoading ? (
            <div className="text-muted-foreground px-4 py-8 text-center text-sm">
              Loading...
            </div>
          ) : negativeItems.length === 0 ? (
            <div className="text-muted-foreground px-4 py-8 text-center text-sm">
              No recent negative feedback.
            </div>
          ) : (
            <div className="divide-y">
              {negativeItems.map((item) => (
                <div
                  key={item.feedback_id}
                  className="grid gap-4 px-4 py-4 text-sm lg:grid-cols-[minmax(160px,0.75fr)_minmax(0,1.45fr)_auto]"
                >
                  <div className="min-w-0 space-y-2">
                    <div className="truncate font-medium">
                      {item.agent_name}
                    </div>
                    <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
                      <ClockIcon className="size-3.5" />
                      {timeText(item.created_at)}
                    </div>
                    <div className="text-muted-foreground flex min-w-0 items-center gap-1.5 text-xs">
                      <MessageSquareIcon className="size-3.5 shrink-0" />
                      <span className="truncate">{channelText(item)}</span>
                    </div>
                    <div className="text-muted-foreground flex min-w-0 items-center gap-1.5 text-xs">
                      <MailIcon className="size-3.5 shrink-0" />
                      <span className="truncate">{voterText(item)}</span>
                    </div>
                    <div className="text-muted-foreground font-mono text-xs">
                      t:{shortId(item.thread_id)} r:{shortId(item.run_id)}
                    </div>
                  </div>

                  <div className="min-w-0 space-y-2">
                    <div>
                      <div className="text-muted-foreground mb-1 flex items-center gap-1.5 text-xs font-medium">
                        <UserIcon className="size-3.5" />
                        User question
                      </div>
                      <p className="line-clamp-2 break-words">
                        {snippetText(item.first_human_message)}
                      </p>
                    </div>
                    <div>
                      <div className="text-muted-foreground mb-1 flex items-center gap-1.5 text-xs font-medium">
                        <BotIcon className="size-3.5" />
                        Assistant answer
                      </div>
                      <p className="text-muted-foreground line-clamp-2 break-words">
                        {snippetText(item.last_ai_message)}
                      </p>
                    </div>
                    {item.comment && (
                      <div className="bg-muted/40 rounded-md px-3 py-2 text-xs">
                        {item.comment}
                      </div>
                    )}
                  </div>

                  <div className="flex items-start lg:justify-end">
                    <Button
                      size="sm"
                      type="button"
                      variant="outline"
                      onClick={() => setSelectedFeedbackId(item.feedback_id)}
                    >
                      <EyeIcon className="size-4" />
                      View
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <Sheet
        open={selectedFeedbackId !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedFeedbackId(null);
          }
        }}
      >
        <SheetContent className="w-full sm:max-w-3xl">
          <SheetHeader className="border-b">
            <SheetTitle>Feedback conversation</SheetTitle>
            <SheetDescription>
              {drawerFeedback
                ? `${drawerFeedback.agent_name} - ${voterText(drawerFeedback)}`
                : "Loading feedback context"}
            </SheetDescription>
          </SheetHeader>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
            {conversationError && (
              <Alert className="mb-4" variant="destructive">
                <AlertCircleIcon />
                <AlertTitle>Conversation unavailable</AlertTitle>
                <AlertDescription>
                  {displayError(conversationError)}
                </AlertDescription>
              </Alert>
            )}

            {drawerFeedback && (
              <div className="grid gap-3 border-b py-4 text-sm sm:grid-cols-4">
                <div>
                  <div className="text-muted-foreground text-xs">User</div>
                  <div className="mt-1 truncate">
                    {voterText(drawerFeedback)}
                  </div>
                </div>
                <div>
                  <div className="text-muted-foreground text-xs">Source</div>
                  <div className="mt-1 truncate">
                    {channelText(drawerFeedback)}
                  </div>
                </div>
                <div>
                  <div className="text-muted-foreground text-xs">Run</div>
                  <div className="mt-1 font-mono text-xs">
                    {shortId(drawerFeedback.run_id)}
                  </div>
                </div>
                <div>
                  <div className="text-muted-foreground text-xs">Messages</div>
                  <div className="mt-1">
                    {numberText(drawerFeedback.message_count)}
                  </div>
                </div>
              </div>
            )}

            {feedbackConversation.isLoading ? (
              <div className="text-muted-foreground py-8 text-center text-sm">
                Loading conversation...
              </div>
            ) : feedbackConversation.conversation?.messages.length ? (
              <div className="divide-y">
                {feedbackConversation.conversation.messages.map(
                  (message, index) => (
                    <div
                      key={`${message.seq ?? index}-${message.event_type}`}
                      className="grid gap-3 py-4 text-sm sm:grid-cols-[120px_minmax(0,1fr)]"
                    >
                      <div className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
                        {messageRole(message) === "Assistant" ? (
                          <BotIcon className="size-4" />
                        ) : (
                          <UserIcon className="size-4" />
                        )}
                        <span>{messageRole(message)}</span>
                      </div>
                      <div className="min-w-0 break-words whitespace-pre-wrap">
                        {extractMessageText(message.content) || "-"}
                      </div>
                    </div>
                  ),
                )}
              </div>
            ) : (
              <div className="text-muted-foreground py-8 text-center text-sm">
                No messages found for this run.
              </div>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </section>
  );
}

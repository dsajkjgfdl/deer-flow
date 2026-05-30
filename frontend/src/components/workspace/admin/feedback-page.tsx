"use client";

import {
  AlertCircleIcon,
  MessageSquareIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useFeedbackSummary, useRecentFeedback } from "@/core/platform";

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

export function FeedbackPage() {
  const feedbackSummary = useFeedbackSummary();
  const recentFeedback = useRecentFeedback(20);
  const feedbackError = feedbackSummary.error ?? recentFeedback.error;
  const summary = feedbackSummary.summary;

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

        <div className="overflow-x-auto rounded-md border">
          <div className="border-b px-4 py-3 text-sm font-medium">
            Recent negative feedback
          </div>
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr className="text-left">
                <th className="px-4 py-3 font-medium">Agent</th>
                <th className="px-4 py-3 font-medium">Target</th>
                <th className="px-4 py-3 font-medium">Comment</th>
              </tr>
            </thead>
            <tbody>
              {recentFeedback.isLoading ? (
                <tr>
                  <td
                    className="text-muted-foreground px-4 py-8 text-center"
                    colSpan={3}
                  >
                    Loading...
                  </td>
                </tr>
              ) : recentFeedback.items.filter((item) => item.rating === -1)
                  .length === 0 ? (
                <tr>
                  <td
                    className="text-muted-foreground px-4 py-8 text-center"
                    colSpan={3}
                  >
                    No recent negative feedback.
                  </td>
                </tr>
              ) : (
                recentFeedback.items
                  .filter((item) => item.rating === -1)
                  .map((item) => (
                    <tr key={item.feedback_id} className="border-t">
                      <td className="px-4 py-3 font-medium">
                        {item.agent_name}
                      </td>
                      <td className="text-muted-foreground px-4 py-3 font-mono text-xs">
                        {item.thread_id} / {item.run_id}
                      </td>
                      <td className="px-4 py-3">{item.comment ?? "-"}</td>
                    </tr>
                  ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

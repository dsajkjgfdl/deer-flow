import type { Message } from "@langchain/langgraph-sdk";

import type { FeedbackData } from "@/core/api/feedback";
import type { ThreadDisplayMessage } from "@/core/threads/types";

export type AssistantFeedbackTarget = {
  runId: string;
  feedback: FeedbackData | null;
};

export function getAssistantFeedbackTarget(
  messages: Message[],
): AssistantFeedbackTarget | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i] as ThreadDisplayMessage;
    if (message.type !== "ai") {
      continue;
    }
    if (typeof message.run_id !== "string" || message.run_id.length === 0) {
      continue;
    }
    return {
      runId: message.run_id,
      feedback: message.feedback ?? null,
    };
  }

  return null;
}

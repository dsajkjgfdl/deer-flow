import type { Message } from "@langchain/langgraph-sdk";
import { expect, test } from "vitest";

import {
  buildFeedbackPayload,
  getAssistantFeedbackTarget,
} from "@/core/messages/feedback";
import type { ThreadDisplayMessage } from "@/core/threads/types";

test("getAssistantFeedbackTarget returns the latest assistant message with run metadata", () => {
  const messages = [
    { id: "human-1", type: "human", content: "Question" } as Message,
    {
      id: "ai-1",
      type: "ai",
      content: "First answer",
      run_id: "run-1",
      feedback: null,
    } as ThreadDisplayMessage,
    {
      id: "ai-2",
      type: "ai",
      content: "Final answer",
      run_id: "run-2",
      feedback: {
        feedback_id: "fb-2",
        rating: -1,
        comment: "wrong",
      },
    } as ThreadDisplayMessage,
  ];

  expect(getAssistantFeedbackTarget(messages)).toEqual({
    runId: "run-2",
    feedback: {
      feedback_id: "fb-2",
      rating: -1,
      comment: "wrong",
    },
  });
});

test("getAssistantFeedbackTarget ignores assistant messages without run metadata", () => {
  const messages = [
    { id: "ai-1", type: "ai", content: "Streaming" } as Message,
  ];

  expect(getAssistantFeedbackTarget(messages)).toBeNull();
});

test("buildFeedbackPayload includes trimmed comment text", () => {
  expect(buildFeedbackPayload(1, " useful answer ")).toEqual({
    rating: 1,
    comment: "useful answer",
  });
  expect(buildFeedbackPayload(-1, "wrong data")).toEqual({
    rating: -1,
    comment: "wrong data",
  });
});

test("buildFeedbackPayload normalizes empty comments to null", () => {
  expect(buildFeedbackPayload(-1, "   ")).toEqual({
    rating: -1,
    comment: null,
  });
  expect(buildFeedbackPayload(1)).toEqual({
    rating: 1,
    comment: null,
  });
});

import type { Message } from "@langchain/langgraph-sdk";
import { expect, test } from "vitest";

import { runMessageToDisplayMessage } from "@/core/threads/hooks";
import type { RunMessage } from "@/core/threads/types";

test("runMessageToDisplayMessage preserves run feedback metadata", () => {
  const content = {
    id: "ai-1",
    type: "ai",
    content: "Answer",
  } as Message;
  const runMessage = {
    run_id: "run-1",
    content,
    metadata: { caller: "lead_agent" },
    created_at: "2026-05-29T00:00:00+08:00",
    feedback: {
      feedback_id: "fb-1",
      rating: 1,
      comment: null,
    },
  } as RunMessage;

  expect(runMessageToDisplayMessage(runMessage)).toEqual({
    ...content,
    run_id: "run-1",
    feedback: {
      feedback_id: "fb-1",
      rating: 1,
      comment: null,
    },
  });
});

import { expect, test } from "vitest";

import { groupNegativeFeedbackByUser } from "@/core/platform/feedback-groups";
import type { FeedbackRecord } from "@/core/platform/types";

function feedback(
  overrides: Partial<FeedbackRecord> & Pick<FeedbackRecord, "feedback_id">,
): FeedbackRecord {
  const base: FeedbackRecord = {
    feedback_id: overrides.feedback_id,
    thread_id: `thread-${overrides.feedback_id}`,
    run_id: `run-${overrides.feedback_id}`,
    user_id: null,
    agent_name: "default",
    rating: -1,
    comment: null,
    created_at: "2026-05-29T00:00:00+00:00",
  };
  return { ...base, ...overrides };
}

test("groupNegativeFeedbackByUser groups negative feedback by voter identity", () => {
  const groups = groupNegativeFeedbackByUser([
    feedback({
      feedback_id: "fb-1",
      user_id: "user-1",
      user_email: "reviewer@example.com",
      agent_name: "hr-boss-agent",
      comment: "wrong data",
      first_human_message: "How many people are in R&D?",
      created_at: "2026-05-29T10:00:00+00:00",
    }),
    feedback({
      feedback_id: "fb-2",
      user_id: "user-1",
      user_email: "reviewer@example.com",
      agent_name: "default",
      created_at: "2026-05-29T12:00:00+00:00",
    }),
    feedback({
      feedback_id: "fb-3",
      source_channel: "wecom",
      platform_user_id: "wx-user-1",
      user_id: "wecom:wx-user-1",
      agent_name: "hr-boss-agent",
      created_at: "2026-05-28T08:00:00+00:00",
    }),
    feedback({
      feedback_id: "fb-positive",
      user_email: "reviewer@example.com",
      rating: 1,
      created_at: "2026-05-30T00:00:00+00:00",
    }),
  ]);

  expect(groups).toHaveLength(2);
  expect(groups[0]).toMatchObject({
    userKey: "web:reviewer@example.com",
    userLabel: "reviewer@example.com",
    count: 2,
    commentCount: 1,
    latestCreatedAt: "2026-05-29T12:00:00+00:00",
    agentNames: ["default", "hr-boss-agent"],
    sourceChannels: ["web"],
  });
  expect(groups[0]?.items.map((item) => item.feedback_id)).toEqual([
    "fb-2",
    "fb-1",
  ]);
  expect(groups[1]).toMatchObject({
    userKey: "wecom:wx-user-1",
    userLabel: "wx-user-1",
    count: 1,
    agentNames: ["hr-boss-agent"],
    sourceChannels: ["wecom"],
  });
});

import { beforeEach, expect, test, vi } from "vitest";

import type { MonitoringRunTimeline } from "@/core/platform/types";

const fetchWithAuth = vi.fn();

vi.mock("@/core/api/fetcher", () => ({
  fetch: fetchWithAuth,
}));

beforeEach(() => {
  fetchWithAuth.mockReset();
});

test("listPlatformUsers requests a paginated admin user page", async () => {
  fetchWithAuth.mockResolvedValue({
    ok: true,
    json: async () => ({
      items: [
        {
          id: "user-1",
          email: "alice@example.com",
          system_role: "user",
          needs_setup: false,
          created_at: "2026-05-29T00:00:00+00:00",
        },
      ],
      total: 12,
      limit: 10,
      offset: 20,
    }),
  });

  const { listPlatformUsers } = await import("@/core/platform/api");

  await expect(
    listPlatformUsers({ limit: 10, offset: 20 }),
  ).resolves.toMatchObject({
    total: 12,
    limit: 10,
    offset: 20,
    items: [{ email: "alice@example.com" }],
  });

  expect(fetchWithAuth).toHaveBeenCalledWith(
    expect.stringContaining("/api/platform/admin/users?limit=10&offset=20"),
  );
});

test("fetchFeedbackSummary requests admin feedback summary", async () => {
  fetchWithAuth.mockResolvedValue({
    ok: true,
    json: async () => ({
      total: 3,
      positive: 2,
      negative: 1,
      positive_rate: 2 / 3,
      by_agent: [
        {
          agent_name: "hr-boss-agent",
          total: 3,
          positive: 2,
          negative: 1,
          positive_rate: 2 / 3,
        },
      ],
    }),
  });

  const { fetchFeedbackSummary } = await import("@/core/platform/api");

  await expect(fetchFeedbackSummary()).resolves.toMatchObject({
    total: 3,
    positive: 2,
    negative: 1,
    by_agent: [{ agent_name: "hr-boss-agent" }],
  });

  expect(fetchWithAuth).toHaveBeenCalledWith(
    expect.stringContaining("/api/platform/admin/feedback/summary"),
  );
});

test("fetchRecentFeedback requests a limited recent feedback page", async () => {
  fetchWithAuth.mockResolvedValue({
    ok: true,
    json: async () => ({
      items: [
        {
          feedback_id: "fb-1",
          thread_id: "thread-1",
          run_id: "run-1",
          user_id: "user-1",
          agent_name: "hr-boss-agent",
          rating: -1,
          comment: "wrong data",
          user_email: "reviewer@example.com",
          run_user_id: "user-1",
          first_human_message: "How many people are in R&D?",
          last_ai_message: "There are 42 people in R&D.",
          message_count: 2,
          created_at: "2026-05-29T00:00:00+00:00",
        },
      ],
    }),
  });

  const { fetchRecentFeedback } = await import("@/core/platform/api");

  await expect(fetchRecentFeedback(5)).resolves.toEqual({
    items: [
      {
        feedback_id: "fb-1",
        thread_id: "thread-1",
        run_id: "run-1",
        user_id: "user-1",
        agent_name: "hr-boss-agent",
        rating: -1,
        comment: "wrong data",
        user_email: "reviewer@example.com",
        run_user_id: "user-1",
        first_human_message: "How many people are in R&D?",
        last_ai_message: "There are 42 people in R&D.",
        message_count: 2,
        created_at: "2026-05-29T00:00:00+00:00",
      },
    ],
  });

  expect(fetchWithAuth).toHaveBeenCalledWith(
    expect.stringContaining("/api/platform/admin/feedback/recent?limit=5"),
  );
});

test("fetchFeedbackConversation requests an admin feedback conversation", async () => {
  fetchWithAuth.mockResolvedValue({
    ok: true,
    json: async () => ({
      feedback: {
        feedback_id: "fb-1",
        thread_id: "thread-1",
        run_id: "run-1",
        user_id: "user-1",
        user_email: "reviewer@example.com",
        agent_name: "hr-boss-agent",
        rating: -1,
        comment: "wrong data",
        first_human_message: "How many people are in R&D?",
        last_ai_message: "There are 42 people in R&D.",
        message_count: 2,
        created_at: "2026-05-29T00:00:00+00:00",
      },
      messages: [
        {
          event_type: "human_message",
          category: "message",
          content: { type: "human", content: "How many people are in R&D?" },
          seq: 1,
        },
      ],
    }),
  });

  const { fetchFeedbackConversation } = await import("@/core/platform/api");

  await expect(fetchFeedbackConversation("fb-1", 50)).resolves.toMatchObject({
    feedback: {
      feedback_id: "fb-1",
      user_email: "reviewer@example.com",
    },
    messages: [{ event_type: "human_message", seq: 1 }],
  });

  expect(fetchWithAuth).toHaveBeenCalledWith(
    expect.stringContaining(
      "/api/platform/admin/feedback/fb-1/conversation?limit=50",
    ),
  );
});

test("fetchRecentMonitoringConversations requests the default recent conversation page", async () => {
  fetchWithAuth.mockResolvedValue({
    ok: true,
    json: async () => ({
      items: [
        {
          identity: {
            identity_type: "channel",
            identity_source: "feishu",
            identity_display: "feishu: ou_xxx",
            raw_identity: { channel_user_id: "ou_xxx", chat_id: "oc_xxx" },
          },
          thread_id: "thread-im",
          latest_run_id: "run-im",
          agent_name: "hr-boss-agent",
          last_message: "研发部门有多少人？",
          status: "error",
          error_summary: "backend unavailable",
          updated_at: "2026-06-08T05:39:22+00:00",
          updated_at_bj: "2026-06-08 13:39:22",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    }),
  });

  const { fetchRecentMonitoringConversations } =
    await import("@/core/platform/api");

  await expect(fetchRecentMonitoringConversations()).resolves.toMatchObject({
    limit: 50,
    items: [
      { thread_id: "thread-im", identity: { identity_source: "feishu" } },
    ],
  });
  expect(fetchWithAuth).toHaveBeenCalledWith(
    expect.stringContaining(
      "/api/platform/admin/monitoring/conversations/recent?limit=50&offset=0",
    ),
  );
});

test("fetchRecentMonitoringConversations normalizes actual backend conversation fields", async () => {
  fetchWithAuth.mockResolvedValue({
    ok: true,
    json: async () => ({
      items: [
        {
          identity: {
            identity_type: "channel",
            identity_source: "feishu",
            identity_display: "feishu: ou_backend",
            raw_identity: { channel_user_id: "ou_backend" },
          },
          thread_id: "thread-backend",
          run_id: "run-backend",
          user_id: "user-backend",
          agent_name: "hr-boss-agent",
          message_count: 3,
          message_preview: "后端实际预览",
          status: "error",
          error: "tool timeout",
          updated_at: "2026-06-08T05:39:22+00:00",
          updated_at_bj: "2026-06-08 13:39:22",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    }),
  });

  const { fetchRecentMonitoringConversations } =
    await import("@/core/platform/api");

  await expect(fetchRecentMonitoringConversations()).resolves.toMatchObject({
    items: [
      {
        thread_id: "thread-backend",
        run_id: "run-backend",
        user_id: "user-backend",
        message_count: 3,
        message_preview: "后端实际预览",
        error: "tool timeout",
        latest_run_id: "run-backend",
        last_message: "后端实际预览",
        error_summary: "tool timeout",
      },
    ],
  });
});

test("fetchMonitoringRunTimeline accepts sparse run_event timeline items", async () => {
  const sparseTimeline = {
    run: { run_id: "run-sparse", thread_id: "thread-sparse" },
    identity: {
      identity_type: "unknown",
      identity_source: "imported",
      identity_display: "unknown/imported",
      raw_identity: {},
    },
    events: [
      {
        seq: 1,
        occurred_at: "2026-06-08T05:39:24+00:00",
        occurred_at_bj: "2026-06-08 13:39:24",
        kind: "message",
        source: "run_event",
        thread_id: "thread-sparse",
        run_id: "run-sparse",
        category: "message",
        content: { text: "hi" },
        metadata: {},
      },
    ],
  } satisfies MonitoringRunTimeline;

  fetchWithAuth.mockResolvedValue({
    ok: true,
    json: async () => sparseTimeline,
  });

  const { fetchMonitoringRunTimeline } = await import("@/core/platform/api");

  await expect(fetchMonitoringRunTimeline("run-sparse")).resolves.toMatchObject(
    {
      events: [
        {
          kind: "message",
          thread_id: "thread-sparse",
          run_id: "run-sparse",
          category: "message",
        },
      ],
    },
  );
});

test("fetchMonitoringRunTimeline requests one run timeline", async () => {
  fetchWithAuth.mockResolvedValue({
    ok: true,
    json: async () => ({
      run: { run_id: "run-im", thread_id: "thread-im", status: "error" },
      identity: {
        identity_type: "channel",
        identity_source: "feishu",
        identity_display: "feishu: ou_xxx",
        raw_identity: { channel_user_id: "ou_xxx" },
      },
      events: [
        {
          seq: 1,
          occurred_at: "2026-06-08T05:39:24+00:00",
          occurred_at_bj: "2026-06-08 13:39:24",
          kind: "tool.error",
          title: "text2cypher_answer_question 调用失败",
          status: "error",
          duration_ms: 842,
          source: "tool_audit",
          tool_name: "text2cypher_answer_question",
          mcp_server_name: "text2cypher",
          content: { error: "timeout" },
          metadata: {},
        },
      ],
    }),
  });

  const { fetchMonitoringRunTimeline } = await import("@/core/platform/api");

  await expect(fetchMonitoringRunTimeline("run-im")).resolves.toMatchObject({
    run: { run_id: "run-im" },
    events: [{ kind: "tool.error" }],
  });
  expect(fetchWithAuth).toHaveBeenCalledWith(
    expect.stringContaining(
      "/api/platform/admin/monitoring/runs/run-im/timeline",
    ),
  );
});

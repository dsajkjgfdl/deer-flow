import { beforeEach, expect, test, vi } from "vitest";

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

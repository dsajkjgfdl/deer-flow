import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test, vi } from "vitest";

import type {
  MonitoringConversationDetail,
  MonitoringRunItem,
} from "@/core/platform";

function run(overrides: Partial<MonitoringRunItem>): MonitoringRunItem {
  return {
    run_id: "run-1",
    thread_id: "thread-1",
    agent_name: "hr-boss-agent",
    status: "success",
    model_name: "qwen3.5-plus",
    message_count: 4,
    first_human_message: "研发部门有多少人？",
    last_ai_message: "研发部门共有 12 人。",
    last_message: "研发部门共有 12 人。",
    message_preview: "研发部门有多少人？",
    total_tokens: 17099,
    llm_call_count: 2,
    error: null,
    created_at: "2026-06-09T06:38:48Z",
    created_at_bj: "2026-06-09 14:38:48",
    updated_at: "2026-06-09T06:39:57Z",
    updated_at_bj: "2026-06-09 14:39:57",
    ...overrides,
  };
}

const conversation: MonitoringConversationDetail = {
  identity: {
    identity_type: "channel",
    identity_source: "wecom",
    identity_display: null,
    raw_identity: {
      channel_user_id: "WuZhongHui",
    },
  },
  thread_id: "thread-1",
  message_preview: "研发部门有多少人？",
  runs: [
    run({ run_id: "run-question", first_human_message: "研发部门有多少人？" }),
    run({
      run_id: "run-fallback",
      first_human_message:
        "<role> Context Extraction Assistant </role><primary_objective>internal</primary_objective>",
      message_preview: "股份公司IT部门有哪些人？",
    }),
  ],
};

describe("ConversationDetail", () => {
  test("shows the concrete user question on each run card", async () => {
    const { ConversationDetail } =
      await import("@/components/platform-admin/monitoring/conversation-detail");

    const markup = renderToStaticMarkup(
      createElement(ConversationDetail, {
        conversation,
        selectedRunId: "run-question",
        isLoading: false,
        onSelectRun: vi.fn(),
      }),
    );

    expect(markup).toContain("Question");
    expect(markup).toContain("研发部门有多少人？");
    expect(markup).toContain("股份公司IT部门有哪些人？");
    expect(markup).not.toContain("Context Extraction Assistant");
  });
});

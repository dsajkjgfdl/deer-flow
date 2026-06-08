import { expect, test } from "vitest";

import { parseImportedRunTimeline } from "@/core/platform/monitoring-import";

import type { MonitoringConversationDetail } from "@/core/platform/types";

test("parseImportedRunTimeline accepts one valid timeline JSON string", () => {
  const parsed = parseImportedRunTimeline(
    JSON.stringify({
      run: { run_id: "run-1", thread_id: "thread-1", status: "success" },
      events: [
        { seq: 1, kind: "run.start", source: "run_event", metadata: {} },
      ],
    }),
  );

  expect(parsed.ok).toBe(true);
  if (parsed.ok) {
    expect(parsed.data.run.run_id).toBe("run-1");
    expect(parsed.data.identity.identity_source).toBe("imported");
  }
});

test("parseImportedRunTimeline accepts sparse run_event timeline JSON", () => {
  const parsed = parseImportedRunTimeline(
    JSON.stringify({
      run: { run_id: "run-1", thread_id: "thread-1" },
      events: [
        {
          seq: 1,
          kind: "message",
          source: "run_event",
          thread_id: "thread-1",
          run_id: "run-1",
          category: "message",
          metadata: {},
        },
      ],
    }),
  );

  expect(parsed.ok).toBe(true);
  if (parsed.ok) {
    expect(parsed.data.events[0]).toMatchObject({
      kind: "message",
      category: "message",
    });
  }
});

test("MonitoringConversationDetail uses backend string message preview", () => {
  const detail: MonitoringConversationDetail = {
    identity: {
      identity_type: "unknown",
      identity_source: "imported",
      identity_display: "unknown/imported",
      raw_identity: {},
    },
    thread_id: "thread-1",
    runs: [],
    message_preview: "后端实际预览",
  };

  expect(detail.message_preview).toBe("后端实际预览");
});

test("parseImportedRunTimeline rejects missing events", () => {
  const parsed = parseImportedRunTimeline(
    JSON.stringify({ run: { run_id: "run-1", thread_id: "thread-1" } }),
  );

  expect(parsed.ok).toBe(false);
  if (!parsed.ok) {
    expect(parsed.error).toContain("events");
  }
});

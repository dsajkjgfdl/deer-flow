import { expect, test } from "vitest";

import { parseImportedRunTimeline } from "@/core/platform/monitoring-import";

import type {
  MonitoringConversationDetail,
  MonitoringRunTimeline,
} from "@/core/platform/types";

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

test("parseImportedRunTimeline accepts imported events with missing or null seq", () => {
  const timelineWithMissingSeq = {
    run: { run_id: "run-missing-seq", thread_id: "thread-1" },
    identity: {
      identity_type: "unknown",
      identity_source: "imported",
      identity_display: "unknown/imported",
      raw_identity: {},
    },
    events: [
      {
        occurred_at: null,
        occurred_at_bj: null,
        kind: "tool.audit",
        source: "tool_audit",
        content: null,
        metadata: {},
      },
    ],
  } satisfies MonitoringRunTimeline;

  const timelineWithNullSeq = {
    run: { run_id: "run-null-seq", thread_id: "thread-1" },
    identity: {
      identity_type: "unknown",
      identity_source: "imported",
      identity_display: "unknown/imported",
      raw_identity: {},
    },
    events: [
      {
        seq: null,
        occurred_at: null,
        occurred_at_bj: null,
        kind: "tool.audit",
        source: "tool_audit",
        content: null,
        metadata: {},
      },
    ],
  } satisfies MonitoringRunTimeline;

  const missingSeqParsed = parseImportedRunTimeline(
    JSON.stringify(timelineWithMissingSeq),
  );
  const nullSeqParsed = parseImportedRunTimeline(
    JSON.stringify(timelineWithNullSeq),
  );

  expect(missingSeqParsed.ok).toBe(true);
  expect(nullSeqParsed.ok).toBe(true);
});

test("parseImportedRunTimeline rejects non-object events", () => {
  const parsed = parseImportedRunTimeline(
    JSON.stringify({
      run: { run_id: "run-1", thread_id: "thread-1" },
      events: [null],
    }),
  );

  expect(parsed.ok).toBe(false);
  if (!parsed.ok) {
    expect(parsed.error).toContain("events[0]");
  }
});

test("parseImportedRunTimeline rejects unsupported event source", () => {
  const parsed = parseImportedRunTimeline(
    JSON.stringify({
      run: { run_id: "run-1", thread_id: "thread-1" },
      events: [{ kind: "run.start", source: "bad", metadata: {} }],
    }),
  );

  expect(parsed.ok).toBe(false);
});

test("parseImportedRunTimeline defaults missing event metadata", () => {
  const parsed = parseImportedRunTimeline(
    JSON.stringify({
      run: { run_id: "run-1", thread_id: "thread-1" },
      events: [{ kind: "run.start", source: "run_event" }],
    }),
  );

  expect(parsed.ok).toBe(true);
  if (parsed.ok) {
    expect(parsed.data.events[0]?.metadata).toEqual({});
  }
});

test("parseImportedRunTimeline rejects invalid event metadata and seq", () => {
  const invalidMetadata = parseImportedRunTimeline(
    JSON.stringify({
      run: { run_id: "run-1", thread_id: "thread-1" },
      events: [{ kind: "run.start", source: "run_event", metadata: "bad" }],
    }),
  );
  const invalidSeq = parseImportedRunTimeline(
    JSON.stringify({
      run: { run_id: "run-1", thread_id: "thread-1" },
      events: [
        { seq: "1", kind: "run.start", source: "run_event", metadata: {} },
      ],
    }),
  );

  expect(invalidMetadata.ok).toBe(false);
  expect(invalidSeq.ok).toBe(false);
});

test("parseImportedRunTimeline falls back when identity object is incomplete", () => {
  const parsed = parseImportedRunTimeline(
    JSON.stringify({
      run: { run_id: "run-1", thread_id: "thread-1" },
      identity: {},
      events: [{ kind: "run.start", source: "run_event", metadata: {} }],
    }),
  );

  expect(parsed.ok).toBe(true);
  if (parsed.ok) {
    expect(parsed.data.identity.identity_source).toBe("imported");
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

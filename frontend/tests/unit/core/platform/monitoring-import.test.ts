import { expect, test } from "vitest";

import { parseImportedRunTimeline } from "@/core/platform/monitoring-import";

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

test("parseImportedRunTimeline rejects missing events", () => {
  const parsed = parseImportedRunTimeline(
    JSON.stringify({ run: { run_id: "run-1", thread_id: "thread-1" } }),
  );

  expect(parsed.ok).toBe(false);
  if (!parsed.ok) {
    expect(parsed.error).toContain("events");
  }
});

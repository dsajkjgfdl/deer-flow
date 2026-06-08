import { describe, expect, test } from "vitest";

import { eventKey } from "@/components/platform-admin/monitoring/format";
import type { MonitoringTimelineEvent } from "@/core/platform";

function timelineEvent(
  overrides: Partial<MonitoringTimelineEvent>,
): MonitoringTimelineEvent {
  return {
    seq: null,
    occurred_at: "2026-06-08T08:00:00Z",
    occurred_at_bj: "2026-06-08 16:00:00",
    kind: "run_event",
    source: "run_event",
    content: {},
    metadata: {},
    ...overrides,
  };
}

describe("monitoring format helpers", () => {
  test("creates non-colliding keys for mixed seq and no-seq events", () => {
    const sequenced = timelineEvent({ seq: 1, kind: "message" });
    const noSeqAtSameIndex = timelineEvent({
      seq: null,
      kind: "tool_call",
      occurred_at: "2026-06-08T08:00:01Z",
      source: "tool_audit",
    });

    expect(eventKey(sequenced, 0)).toBe("seq:1");
    expect(eventKey(noSeqAtSameIndex, 1)).toBe(
      "idx:1:tool_call:2026-06-08T08:00:01Z",
    );
    expect(eventKey(noSeqAtSameIndex, 1)).not.toBe(eventKey(sequenced, 0));
  });
});

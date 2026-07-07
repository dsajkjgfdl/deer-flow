import { describe, expect, test } from "@rstest/core";

import type { MonitoringRunTimeline } from "@/core/platform";
import {
  formatRunTimelineAsJSON,
  runTimelineExportFilename,
} from "@/core/platform/monitoring-export";

const timeline: MonitoringRunTimeline = {
  run: {
    run_id: "run/with:unsafe*chars",
    thread_id: "thread-1",
    status: "success",
    last_ai_message: "研发部门共有 12 人。",
  },
  identity: {
    identity_type: "channel",
    identity_source: "wecom",
    identity_display: null,
    raw_identity: {
      channel_user_id: "WuZhongHui",
    },
  },
  events: [
    {
      seq: 1,
      occurred_at: "2026-06-09T06:02:09Z",
      occurred_at_bj: "2026-06-09 14:02:09",
      kind: "tool.end",
      title: "tool.end",
      status: "success",
      duration_ms: 120,
      source: "tool_audit",
      thread_id: "thread-1",
      run_id: "run/with:unsafe*chars",
      category: "tool",
      tool_name: "text2cypher_answer_question",
      mcp_server_name: "text2cypher",
      content: {
        result: {
          execution: {
            records: [{ count: 12 }],
          },
        },
      },
      metadata: {
        tool_call_id: "call-1",
      },
    },
  ],
};

describe("monitoring run timeline export", () => {
  test("formats a complete run timeline JSON payload", () => {
    const json = formatRunTimelineAsJSON(
      timeline,
      "2026-06-23T08:30:00.000Z",
    );
    const parsed = JSON.parse(json) as MonitoringRunTimeline & {
      exported_at: string;
    };

    expect(parsed.exported_at).toBe("2026-06-23T08:30:00.000Z");
    expect(parsed.run).toEqual(timeline.run);
    expect(parsed.identity).toEqual(timeline.identity);
    expect(parsed.events).toEqual(timeline.events);
    expect(parsed.events[0]?.content).toEqual(timeline.events[0]?.content);
    expect(parsed.events[0]?.metadata).toEqual(timeline.events[0]?.metadata);
  });

  test("builds a safe JSON filename from the run id", () => {
    expect(runTimelineExportFilename(timeline)).toBe(
      "run-timeline-run-with-unsafe-chars.json",
    );
  });
});

import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test, vi } from "vitest";

import type {
  MonitoringRunTimeline,
  MonitoringTimelineEvent,
} from "@/core/platform";

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children, open }: { children?: ReactNode; open?: boolean }) =>
    createElement("div", { "data-open": open }, children),
  DialogContent: ({
    children,
    className,
  }: {
    children?: ReactNode;
    className?: string;
  }) => createElement("div", { className }, children),
  DialogDescription: ({ children }: { children?: ReactNode }) =>
    createElement("p", null, children),
  DialogHeader: ({
    children,
    className,
  }: {
    children?: ReactNode;
    className?: string;
  }) => createElement("header", { className }, children),
  DialogTitle: ({ children }: { children?: ReactNode }) =>
    createElement("h2", null, children),
}));

const event: MonitoringTimelineEvent = {
  seq: 1,
  occurred_at: "2026-06-09T06:02:09Z",
  occurred_at_bj: "2026-06-09 14:02:09",
  kind: "run.start",
  title: "run.start",
  status: "running",
  duration_ms: null,
  source: "run_event",
  thread_id: "thread-wecom",
  run_id: "bd8d6070-2",
  category: "lifecycle",
  tool_name: null,
  mcp_server_name: null,
  content: { input: "test" },
  metadata: { channel: "wecom" },
};

const timeline: MonitoringRunTimeline = {
  run: {
    run_id: "bd8d6070-2",
    thread_id: "thread-wecom",
    status: "running",
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
  events: [event],
};

describe("RunInspectionDialog", () => {
  test("renders timeline and inspector in a near-full-screen troubleshooting dialog", async () => {
    const { RunInspectionDialog } =
      await import("@/components/platform-admin/monitoring/run-inspection-dialog");

    const markup = renderToStaticMarkup(
      createElement(RunInspectionDialog, {
        open: true,
        onOpenChange: vi.fn(),
        runId: timeline.run.run_id,
        identity: timeline.identity,
        timeline,
        selectedEventKey: "seq:1",
        onSelectEventKey: vi.fn(),
        selectedEvent: event,
        isLoading: false,
        isImported: false,
      }),
    );

    expect(markup).toContain("Run inspection");
    expect(markup).toContain("bd8d6070-2");
    expect(markup).toContain("wecom/WuZhongHui");
    expect(markup).toContain("Run timeline");
    expect(markup).toContain("Event inspector");
    expect(markup).toContain("Final response");
    expect(markup).toContain("研发部门共有 12 人。");
    expect(markup).toContain("max-w-[calc(100vw-2rem)]");
    expect(markup).toContain(
      "lg:grid-cols-[minmax(320px,0.85fr)_minmax(0,1.5fr)]",
    );
  });

  test("keeps run context visible while the timeline request is still loading", async () => {
    const { RunInspectionDialog } =
      await import("@/components/platform-admin/monitoring/run-inspection-dialog");

    const markup = renderToStaticMarkup(
      createElement(RunInspectionDialog, {
        open: true,
        onOpenChange: vi.fn(),
        runId: "run-loading",
        identity: timeline.identity,
        timeline: null,
        selectedEventKey: null,
        onSelectEventKey: vi.fn(),
        selectedEvent: null,
        isLoading: true,
        isImported: false,
      }),
    );

    expect(markup).toContain("run-loading");
    expect(markup).toContain("wecom/WuZhongHui");
    expect(markup).toContain("Loading...");
    expect(markup).not.toContain("No timeline events.");
  });
});

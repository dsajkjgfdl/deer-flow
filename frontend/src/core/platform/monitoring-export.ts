import { downloadAsFile } from "@/core/threads/export";

import type { MonitoringRunTimeline } from "./types";

function safeFilenamePart(value: string): string {
  return (
    value
      .replace(/[^\p{L}\p{N}_-]+/gu, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "") || "run"
  );
}

export function runTimelineExportFilename(
  timeline: MonitoringRunTimeline,
): string {
  return `run-timeline-${safeFilenamePart(timeline.run.run_id)}.json`;
}

export function formatRunTimelineAsJSON(
  timeline: MonitoringRunTimeline,
  exportedAt = new Date().toISOString(),
): string {
  return JSON.stringify(
    {
      exported_at: exportedAt,
      run: timeline.run,
      identity: timeline.identity,
      events: timeline.events,
    },
    null,
    2,
  );
}

export function exportRunTimelineAsJSON(timeline: MonitoringRunTimeline) {
  downloadAsFile(
    formatRunTimelineAsJSON(timeline),
    runTimelineExportFilename(timeline),
    "application/json;charset=utf-8",
  );
}

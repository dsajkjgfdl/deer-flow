import { readFileSync } from "node:fs";

import { describe, expect, test } from "@rstest/core";

const source = readFileSync(
  "src/components/platform-admin/monitoring/agent-monitoring-page.tsx",
  "utf8",
);
const hooksSource = readFileSync("src/core/platform/hooks.ts", "utf8");

describe("AgentMonitoringPage run inspection wiring", () => {
  test("opens the run inspection dialog from run selection and imported timelines", () => {
    expect(source).toContain(
      'import { RunInspectionDialog } from "./run-inspection-dialog";',
    );
    expect(source).toMatch(
      /function handleSelectRun\(runId: string\)[\s\S]*?setRunInspectionOpen\(true\);[\s\S]*?\n  }/,
    );
    expect(source).toMatch(
      /function handleImported\(timeline: MonitoringRunTimeline\)[\s\S]*?setRunInspectionOpen\(true\);[\s\S]*?\n  }/,
    );
    expect(source).toContain("<RunInspectionDialog");
    expect(source).toContain("Inspect run");
    expect(source).toContain("onClick={() => setRunInspectionOpen(true)}");
  });

  test("keeps the main page focused on conversations and runs", () => {
    expect(source).not.toContain("import { RunTimeline }");
    expect(source).not.toContain("import { EventInspector }");
    expect(source).not.toContain("<RunTimeline");
    expect(source).not.toContain("<EventInspector");
    expect(source).toContain("lg:grid-cols-[360px_minmax(520px,1fr)]");
  });

  test("refreshes selected conversation while a run is active", () => {
    expect(hooksSource).toContain("MONITORING_ACTIVE_RUN_STATUSES");
    expect(hooksSource).toMatch(
      /useMonitoringConversation[\s\S]*?refetchInterval:[\s\S]*?MONITORING_ACTIVE_RUN_STATUSES/,
    );
  });
});

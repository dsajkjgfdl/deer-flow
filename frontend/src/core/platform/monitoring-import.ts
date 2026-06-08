import type {
  MonitoringIdentity,
  MonitoringRunItem,
  MonitoringRunTimeline,
  MonitoringTimelineEvent,
} from "./types";

export type ImportedRunTimelineResult =
  | { ok: true; data: MonitoringRunTimeline }
  | { ok: false; error: string };

const DEFAULT_IMPORTED_IDENTITY: MonitoringIdentity = {
  identity_type: "unknown",
  identity_source: "imported",
  identity_display: "unknown/imported",
  raw_identity: {},
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export function parseImportedRunTimeline(
  input: string,
): ImportedRunTimelineResult {
  let parsed: unknown;

  try {
    parsed = JSON.parse(input);
  } catch {
    return { ok: false, error: "JSON 格式无效" };
  }

  if (!isRecord(parsed)) {
    return { ok: false, error: "根节点必须是对象" };
  }

  if (!isRecord(parsed.run)) {
    return { ok: false, error: "run 必须是对象" };
  }

  const runId = parsed.run.run_id;
  if (!isNonEmptyString(runId)) {
    return { ok: false, error: "run.run_id 必须是非空字符串" };
  }

  const threadId = parsed.run.thread_id;
  if (!isNonEmptyString(threadId)) {
    return { ok: false, error: "run.thread_id 必须是非空字符串" };
  }

  if (!Array.isArray(parsed.events)) {
    return { ok: false, error: "events 必须是数组" };
  }

  const identity = isRecord(parsed.identity)
    ? (parsed.identity as unknown as MonitoringIdentity)
    : DEFAULT_IMPORTED_IDENTITY;

  return {
    ok: true,
    data: {
      run: {
        ...(parsed.run as Partial<MonitoringRunItem>),
        run_id: runId,
        thread_id: threadId,
      },
      identity,
      events: parsed.events as MonitoringTimelineEvent[],
    },
  };
}

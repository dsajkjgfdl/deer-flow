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

function isMonitoringIdentityType(
  value: unknown,
): value is MonitoringIdentity["identity_type"] {
  return value === "web" || value === "channel" || value === "unknown";
}

function isNullableString(value: unknown): value is string | null {
  return typeof value === "string" || value === null;
}

function parseIdentity(value: unknown): MonitoringIdentity {
  if (!isRecord(value)) {
    return DEFAULT_IMPORTED_IDENTITY;
  }

  if (
    !isMonitoringIdentityType(value.identity_type) ||
    !("identity_source" in value) ||
    !isNullableString(value.identity_source) ||
    !("identity_display" in value) ||
    !isNullableString(value.identity_display) ||
    !isRecord(value.raw_identity)
  ) {
    return DEFAULT_IMPORTED_IDENTITY;
  }

  return {
    identity_type: value.identity_type,
    identity_source: value.identity_source,
    identity_display: value.identity_display,
    raw_identity: value.raw_identity as Record<string, string | null>,
  };
}

function parseTimelineEvent(
  value: unknown,
  index: number,
): { ok: true; event: MonitoringTimelineEvent } | { ok: false; error: string } {
  if (!isRecord(value)) {
    return { ok: false, error: `events[${index}] 必须是对象` };
  }

  if (!isNonEmptyString(value.kind)) {
    return { ok: false, error: `events[${index}].kind 必须是非空字符串` };
  }

  if (value.source !== "run_event" && value.source !== "tool_audit") {
    return {
      ok: false,
      error: `events[${index}].source 必须是 run_event 或 tool_audit`,
    };
  }

  if (
    value.seq !== undefined &&
    value.seq !== null &&
    typeof value.seq !== "number"
  ) {
    return { ok: false, error: `events[${index}].seq 必须是数字` };
  }

  if (value.metadata !== undefined && !isRecord(value.metadata)) {
    return { ok: false, error: `events[${index}].metadata 必须是对象` };
  }

  return {
    ok: true,
    event: {
      ...value,
      kind: value.kind,
      source: value.source,
      metadata: value.metadata ?? {},
    } as MonitoringTimelineEvent,
  };
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

  const events: MonitoringTimelineEvent[] = [];
  for (const [index, event] of parsed.events.entries()) {
    const normalized = parseTimelineEvent(event, index);
    if (!normalized.ok) {
      return { ok: false, error: normalized.error };
    }
    events.push(normalized.event);
  }

  const identity = parseIdentity(parsed.identity);

  return {
    ok: true,
    data: {
      run: {
        ...(parsed.run as Partial<MonitoringRunItem>),
        run_id: runId,
        thread_id: threadId,
      },
      identity,
      events,
    },
  };
}

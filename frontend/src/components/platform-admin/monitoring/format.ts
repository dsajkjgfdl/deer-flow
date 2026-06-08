import type {
  MonitoringIdentity,
  MonitoringTimelineEvent,
} from "@/core/platform";

export function shortId(value?: string | null): string {
  const text = value?.trim();
  if (!text) return "-";
  return text.length > 10 ? text.slice(0, 10) : text;
}

export function statusVariant(
  status?: string | null,
): "default" | "secondary" | "destructive" | "outline" {
  const normalized = status?.toLowerCase();
  if (!normalized) return "outline";
  if (
    normalized.includes("error") ||
    normalized.includes("fail") ||
    normalized.includes("timeout")
  ) {
    return "destructive";
  }
  if (
    normalized.includes("success") ||
    normalized.includes("complete") ||
    normalized.includes("done")
  ) {
    return "default";
  }
  if (
    normalized.includes("running") ||
    normalized.includes("pending") ||
    normalized.includes("start")
  ) {
    return "secondary";
  }
  return "outline";
}

function firstRawIdentityValue(identity: MonitoringIdentity): string | null {
  for (const value of Object.values(identity.raw_identity ?? {})) {
    const text = value?.trim();
    if (text) return text;
  }
  return null;
}

export function identityText(identity?: MonitoringIdentity | null): string {
  if (!identity) return "-";

  const source = identity.identity_source?.trim();
  const display = identity.identity_display?.trim();
  const rawValue = firstRawIdentityValue(identity);

  if (identity.identity_type === "channel") {
    if (source && rawValue) return `${source}/${rawValue}`;
    return rawValue ?? source ?? "channel";
  }

  if (display) return display;
  if (source && rawValue) return `${source}/${rawValue}`;
  return rawValue ?? source ?? identity.identity_type ?? "-";
}

export function durationText(value?: number | null): string {
  if (value == null) return "-";
  if (value < 1000) return `${Math.round(value)} ms`;
  if (value < 60_000) return `${(value / 1000).toFixed(1)} s`;
  return `${(value / 60_000).toFixed(1)} min`;
}

export function eventTone(event: MonitoringTimelineEvent): string {
  const normalized = event.status?.toLowerCase() ?? "";
  if (
    normalized.includes("error") ||
    normalized.includes("fail") ||
    normalized.includes("timeout")
  ) {
    return "border-destructive/40 bg-destructive/5";
  }
  if (event.source === "tool_audit" || event.tool_name) {
    return "border-blue-500/30 bg-blue-500/5";
  }
  if (normalized.includes("success") || normalized.includes("complete")) {
    return "border-primary/25 bg-primary/5";
  }
  return "border-border bg-background";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isSensitiveKey(key: string): boolean {
  const normalized = key.toLowerCase().replace(/[\s-]+/g, "_");
  return (
    normalized.includes("password") ||
    normalized.includes("token") ||
    normalized.includes("secret") ||
    normalized.includes("api_key") ||
    normalized.includes("apikey") ||
    normalized.includes("authorization")
  );
}

function maskSensitiveJsonInner(value: unknown, seen: WeakSet<object>): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => maskSensitiveJsonInner(item, seen));
  }

  if (!isRecord(value)) {
    return value;
  }

  if (seen.has(value)) {
    return "[Circular]";
  }
  seen.add(value);

  const masked: Record<string, unknown> = {};
  for (const [key, nestedValue] of Object.entries(value)) {
    masked[key] = isSensitiveKey(key)
      ? "[REDACTED]"
      : maskSensitiveJsonInner(nestedValue, seen);
  }
  return masked;
}

export function maskSensitiveJson(value: unknown): unknown {
  return maskSensitiveJsonInner(value, new WeakSet<object>());
}

export function timeText(value?: string | null): string {
  const text = value?.trim();
  if (!text) return "-";
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

export function numberText(value?: number | null): string {
  if (value == null) return "-";
  return new Intl.NumberFormat().format(value);
}

export function jsonText(value: unknown): string {
  return JSON.stringify(maskSensitiveJson(value), null, 2);
}

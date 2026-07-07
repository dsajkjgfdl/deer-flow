import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

import type {
  AdminAuditItem,
  AgentCatalogEntry,
  AssignmentMutationResult,
  FeedbackConversation,
  FeedbackRecord,
  FeedbackSummary,
  MonitoringConversationItem,
  MonitoringConversationDetail,
  MonitoringConversationsPage,
  MonitoringRunTimeline,
  PlatformAgent,
  PlatformUsersPage,
  RunMonitoringItem,
  ToolFailureItem,
  ToolMonitoringItem,
  UserAgentAssignments,
} from "./types";

export interface MonitoringConversationFilters {
  limit?: number;
  offset?: number;
  source?: string;
  agent_name?: string;
  status?: string;
  tool_name?: string;
  mcp_server_name?: string;
  q?: string;
  from?: string;
  to?: string;
}

async function readJsonOrThrow<T>(res: Response, fallback: string): Promise<T> {
  if (res.ok) return res.json() as Promise<T>;
  const err = (await res.json().catch(() => ({}))) as { detail?: string };
  throw new Error(err.detail ?? fallback);
}

function normalizeMonitoringConversationItem(
  item: MonitoringConversationItem,
): MonitoringConversationItem {
  return {
    ...item,
    latest_run_id: item.latest_run_id ?? item.run_id ?? null,
    last_message: item.last_message ?? item.message_preview ?? null,
    error_summary: item.error_summary ?? item.error ?? null,
  };
}

export async function listAgentCatalog(): Promise<AgentCatalogEntry[]> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/platform/admin/agents/catalog`,
  );
  const data = await readJsonOrThrow<{ agents: AgentCatalogEntry[] }>(
    res,
    `Failed to load agent catalog: ${res.statusText}`,
  );
  return data.agents;
}

export async function listRunnableAgents(): Promise<PlatformAgent[]> {
  const res = await fetch(`${getBackendBaseURL()}/api/platform/agents`);
  const data = await readJsonOrThrow<{ agents: PlatformAgent[] }>(
    res,
    `Failed to load platform agents: ${res.statusText}`,
  );
  return data.agents;
}

export async function listPlatformUsers({
  limit,
  offset,
}: {
  limit: number;
  offset: number;
}): Promise<PlatformUsersPage> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  const res = await fetch(
    `${getBackendBaseURL()}/api/platform/admin/users?${params.toString()}`,
  );
  return readJsonOrThrow<PlatformUsersPage>(
    res,
    `Failed to load users: ${res.statusText}`,
  );
}

export async function listUserAgentAssignments(
  userId: string,
): Promise<UserAgentAssignments> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/platform/admin/users/${encodeURIComponent(userId)}/agents`,
  );
  return readJsonOrThrow<UserAgentAssignments>(
    res,
    `Failed to load assignments: ${res.statusText}`,
  );
}

export async function grantUserAgent(
  userId: string,
  agentName: string,
): Promise<AssignmentMutationResult> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/platform/admin/users/${encodeURIComponent(userId)}/agents/${encodeURIComponent(agentName)}`,
    { method: "PUT" },
  );
  return readJsonOrThrow<AssignmentMutationResult>(
    res,
    `Failed to grant agent: ${res.statusText}`,
  );
}

export async function revokeUserAgent(
  userId: string,
  agentName: string,
): Promise<AssignmentMutationResult> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/platform/admin/users/${encodeURIComponent(userId)}/agents/${encodeURIComponent(agentName)}`,
    { method: "DELETE" },
  );
  return readJsonOrThrow<AssignmentMutationResult>(
    res,
    `Failed to revoke agent: ${res.statusText}`,
  );
}

export async function listAdminAudit(limit = 100): Promise<AdminAuditItem[]> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/platform/admin/audit?limit=${limit}`,
  );
  const data = await readJsonOrThrow<{ items: AdminAuditItem[] }>(
    res,
    `Failed to load audit logs: ${res.statusText}`,
  );
  return data.items;
}

export async function listRunMonitoring(): Promise<RunMonitoringItem[]> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/platform/admin/monitoring/runs`,
  );
  const data = await readJsonOrThrow<{ items: RunMonitoringItem[] }>(
    res,
    `Failed to load run monitoring: ${res.statusText}`,
  );
  return data.items;
}

export async function listToolMonitoring(): Promise<{
  items: ToolMonitoringItem[];
  recent_failures: ToolFailureItem[];
}> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/platform/admin/monitoring/tools`,
  );
  return readJsonOrThrow<{
    items: ToolMonitoringItem[];
    recent_failures: ToolFailureItem[];
  }>(res, `Failed to load tool monitoring: ${res.statusText}`);
}

export async function fetchRecentMonitoringConversations(
  filters: MonitoringConversationFilters = {},
): Promise<MonitoringConversationsPage> {
  const { limit = 50, offset = 0, ...optionalFilters } = filters;
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });

  for (const [key, value] of Object.entries(optionalFilters)) {
    if (value === undefined || value === null) continue;
    if (typeof value === "string" && value.trim() === "") continue;
    params.set(key, String(value));
  }

  const res = await fetch(
    `${getBackendBaseURL()}/api/platform/admin/monitoring/conversations/recent?${params.toString()}`,
  );
  const page = await readJsonOrThrow<MonitoringConversationsPage>(
    res,
    `Failed to load monitoring conversations: ${res.statusText}`,
  );
  return {
    ...page,
    items: page.items.map(normalizeMonitoringConversationItem),
  };
}

export async function fetchMonitoringConversation(
  threadId: string,
): Promise<MonitoringConversationDetail> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/platform/admin/monitoring/conversations/${encodeURIComponent(threadId)}`,
  );
  return readJsonOrThrow<MonitoringConversationDetail>(
    res,
    `Failed to load monitoring conversation: ${res.statusText}`,
  );
}

export async function fetchMonitoringRunTimeline(
  runId: string,
): Promise<MonitoringRunTimeline> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/platform/admin/monitoring/runs/${encodeURIComponent(runId)}/timeline`,
  );
  return readJsonOrThrow<MonitoringRunTimeline>(
    res,
    `Failed to load monitoring run timeline: ${res.statusText}`,
  );
}

export async function fetchFeedbackSummary(): Promise<FeedbackSummary> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/platform/admin/feedback/summary`,
  );
  return readJsonOrThrow<FeedbackSummary>(
    res,
    `Failed to load feedback summary: ${res.statusText}`,
  );
}

export async function fetchRecentFeedback(
  limit = 20,
): Promise<{ items: FeedbackRecord[] }> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/platform/admin/feedback/recent?limit=${limit}`,
  );
  return readJsonOrThrow<{ items: FeedbackRecord[] }>(
    res,
    `Failed to load recent feedback: ${res.statusText}`,
  );
}

export async function fetchFeedbackConversation(
  feedbackId: string,
  limit = 100,
): Promise<FeedbackConversation> {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(
    `${getBackendBaseURL()}/api/platform/admin/feedback/${encodeURIComponent(feedbackId)}/conversation?${params.toString()}`,
  );
  return readJsonOrThrow<FeedbackConversation>(
    res,
    `Failed to load feedback conversation: ${res.statusText}`,
  );
}

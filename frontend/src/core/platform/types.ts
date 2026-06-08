export type AgentCatalogStatus = "valid" | "warning" | "invalid";

export interface AgentCatalogEntry {
  name: string;
  display_name: string | null;
  description: string;
  model: string | null;
  tool_groups: string[] | null;
  skills: string[] | null;
  mcp_servers: string[] | null;
  config_path: string;
  soul_path: string | null;
  config_hash: string;
  soul_hash: string | null;
  git_commit: string | null;
  status: AgentCatalogStatus;
  validation_errors: string[];
  validation_warnings: string[];
}

export interface PlatformAgent {
  name: string;
  display_name: string | null;
  description: string;
  model: string | null;
  tool_groups: string[] | null;
  skills: string[] | null;
  mcp_servers: string[] | null;
  status: AgentCatalogStatus;
  validation_errors: string[];
  validation_warnings: string[];
}

export interface UserAgentAssignments {
  user_id: string;
  agent_names: string[];
}

export interface PlatformUser {
  id: string;
  email: string;
  system_role: "admin" | "user";
  needs_setup: boolean;
  created_at: string;
}

export interface PlatformUsersPage {
  items: PlatformUser[];
  total: number;
  limit: number;
  offset: number;
}

export interface AssignmentMutationResult {
  user_id: string;
  agent_name: string;
  granted?: boolean;
  revoked?: boolean;
}

export interface AdminAuditItem {
  id?: number;
  actor_user_id: string;
  action: string;
  target_user_id: string | null;
  target_agent_name: string | null;
  metadata_json?: Record<string, unknown>;
  created_at?: string;
}

export interface RunMonitoringItem {
  agent_name: string;
  run_count: number;
  success_count: number;
  error_count: number;
  total_tokens: number;
  llm_call_count: number;
}

export interface ToolMonitoringItem {
  agent_name: string;
  mcp_server_name: string | null;
  tool_name: string;
  call_count: number;
  error_count: number;
  avg_latency_ms: number | null;
}

export interface ToolFailureItem {
  id?: number;
  run_id: string | null;
  thread_id: string | null;
  user_id: string | null;
  agent_name: string | null;
  tool_name: string;
  mcp_server_name: string | null;
  status: string;
  latency_ms: number | null;
  error: string | null;
  metadata_json?: Record<string, unknown>;
  created_at?: string;
}

export interface FeedbackAgentSummary {
  agent_name: string;
  total: number;
  positive: number;
  negative: number;
  positive_rate: number;
}

export interface FeedbackSummary {
  total: number;
  positive: number;
  negative: number;
  positive_rate: number;
  by_agent: FeedbackAgentSummary[];
}

export interface FeedbackRecord {
  feedback_id: string;
  thread_id: string;
  run_id: string;
  user_id: string | null;
  user_email?: string | null;
  source_channel?: string | null;
  platform_user_id?: string | null;
  platform_chat_id?: string | null;
  platform_message_id?: string | null;
  platform_feedback_id?: string | null;
  run_user_id?: string | null;
  agent_name: string;
  rating: number;
  comment: string | null;
  first_human_message?: string | null;
  last_ai_message?: string | null;
  message_count?: number;
  created_at?: string;
}

export interface FeedbackConversationMessage {
  thread_id?: string;
  run_id?: string;
  event_type: string;
  category?: string;
  content?: unknown;
  metadata?: Record<string, unknown>;
  seq?: number;
  created_at?: string;
}

export interface FeedbackConversation {
  feedback: FeedbackRecord;
  messages: FeedbackConversationMessage[];
}

export type MonitoringIdentityType = "web" | "channel" | "unknown";

export interface MonitoringIdentity {
  identity_type: MonitoringIdentityType;
  identity_source: string;
  identity_display: string;
  raw_identity: Record<string, string | null>;
}

export interface MonitoringConversationItem {
  identity: MonitoringIdentity;
  thread_id: string;
  latest_run_id: string | null;
  run_id?: string | null;
  user_id?: string | null;
  agent_name: string | null;
  last_message: string | null;
  message_count?: number | null;
  message_preview?: string | null;
  status: string | null;
  error_summary: string | null;
  error?: string | null;
  updated_at: string | null;
  updated_at_bj: string | null;
}

export interface MonitoringRunItem {
  run_id: string;
  thread_id: string;
  agent_name: string | null;
  status: string;
  model_name: string | null;
  message_count: number;
  first_human_message: string | null;
  last_ai_message: string | null;
  total_tokens: number;
  llm_call_count: number;
  error: string | null;
  created_at: string | null;
  created_at_bj: string | null;
  updated_at: string | null;
  updated_at_bj: string | null;
}

export interface MonitoringTimelineEvent {
  seq: number;
  occurred_at: string | null;
  occurred_at_bj: string | null;
  kind: string;
  title?: string | null;
  status?: string | null;
  duration_ms?: number | null;
  source: "run_event" | "tool_audit";
  thread_id?: string | null;
  run_id?: string | null;
  category?: string | null;
  tool_name?: string | null;
  mcp_server_name?: string | null;
  content: unknown;
  metadata: Record<string, unknown>;
}

export interface MonitoringConversationsPage {
  items: MonitoringConversationItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface MonitoringConversationDetail {
  identity: MonitoringIdentity;
  thread_id: string;
  runs: MonitoringRunItem[];
  message_preview: string | null;
}

export interface MonitoringRunTimeline {
  run: Partial<MonitoringRunItem> & { run_id: string; thread_id: string };
  identity: MonitoringIdentity;
  events: MonitoringTimelineEvent[];
}

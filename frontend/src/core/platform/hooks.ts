import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchFeedbackSummary,
  fetchRecentFeedback,
  grantUserAgent,
  listAdminAudit,
  listAgentCatalog,
  listPlatformUsers,
  listRunMonitoring,
  listRunnableAgents,
  listToolMonitoring,
  listUserAgentAssignments,
  revokeUserAgent,
} from "./api";

export function useAgentCatalog() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["platform", "admin", "agents", "catalog"],
    queryFn: () => listAgentCatalog(),
  });
  return { agents: data ?? [], isLoading, error };
}

export function useRunnableAgents() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["platform", "agents"],
    queryFn: () => listRunnableAgents(),
  });
  return { agents: data ?? [], isLoading, error };
}

export function usePlatformUsers(limit: number, offset: number) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["platform", "admin", "users", { limit, offset }],
    queryFn: () => listPlatformUsers({ limit, offset }),
  });
  return {
    users: data?.items ?? [],
    total: data?.total ?? 0,
    limit: data?.limit ?? limit,
    offset: data?.offset ?? offset,
    isLoading,
    error,
  };
}

export function useUserAgentAssignments(userId: string | null) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["platform", "admin", "users", userId, "agents"],
    queryFn: () => listUserAgentAssignments(userId!),
    enabled: Boolean(userId),
  });
  return { assignments: data ?? null, isLoading, error };
}

export function useGrantUserAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      userId,
      agentName,
    }: {
      userId: string;
      agentName: string;
    }) => grantUserAgent(userId, agentName),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: ["platform", "admin", "users", variables.userId, "agents"],
      });
      void queryClient.invalidateQueries({
        queryKey: ["platform", "admin", "audit"],
      });
    },
  });
}

export function useRevokeUserAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      userId,
      agentName,
    }: {
      userId: string;
      agentName: string;
    }) => revokeUserAgent(userId, agentName),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: ["platform", "admin", "users", variables.userId, "agents"],
      });
      void queryClient.invalidateQueries({
        queryKey: ["platform", "admin", "audit"],
      });
    },
  });
}

export function useAdminAudit() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["platform", "admin", "audit"],
    queryFn: () => listAdminAudit(),
  });
  return { items: data ?? [], isLoading, error };
}

export function useRunMonitoring() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["platform", "admin", "monitoring", "runs"],
    queryFn: () => listRunMonitoring(),
  });
  return { items: data ?? [], isLoading, error };
}

export function useToolMonitoring() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["platform", "admin", "monitoring", "tools"],
    queryFn: () => listToolMonitoring(),
  });
  return {
    items: data?.items ?? [],
    recentFailures: data?.recent_failures ?? [],
    isLoading,
    error,
  };
}

export function useFeedbackSummary() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["platform", "admin", "feedback", "summary"],
    queryFn: () => fetchFeedbackSummary(),
  });
  return {
    summary: data ?? {
      total: 0,
      positive: 0,
      negative: 0,
      positive_rate: 0,
      by_agent: [],
    },
    isLoading,
    error,
  };
}

export function useRecentFeedback(limit = 20) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["platform", "admin", "feedback", "recent", limit],
    queryFn: () => fetchRecentFeedback(limit),
  });
  return { items: data?.items ?? [], isLoading, error };
}

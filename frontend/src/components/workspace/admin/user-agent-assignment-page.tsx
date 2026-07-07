"use client";

import {
  AlertCircleIcon,
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  PlusIcon,
  ShieldIcon,
  Trash2Icon,
  UserRoundIcon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  useAgentCatalog,
  useGrantUserAgent,
  usePlatformUsers,
  useRevokeUserAgent,
  useUserAgentAssignments,
} from "@/core/platform";
import { cn } from "@/lib/utils";

const USER_PAGE_SIZE = 10;

function displayError(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function roleLabel(role: string) {
  return role === "admin" ? "Admin" : "User";
}

export function UserAgentAssignmentPage() {
  const [pageIndex, setPageIndex] = useState(0);
  const [activeUserId, setActiveUserId] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState("");
  const userOffset = pageIndex * USER_PAGE_SIZE;
  const {
    users,
    total,
    isLoading: isUsersLoading,
    error: usersError,
  } = usePlatformUsers(USER_PAGE_SIZE, userOffset);
  const { agents } = useAgentCatalog();
  const validAgents = useMemo(
    () => agents.filter((agent) => agent.status !== "invalid"),
    [agents],
  );
  const selectedUser = users.find((user) => user.id === activeUserId) ?? null;
  const selectedUserId = selectedUser?.id ?? null;
  const {
    assignments,
    isLoading: isAssignmentsLoading,
    error: assignmentsError,
  } = useUserAgentAssignments(selectedUserId);
  const grantMutation = useGrantUserAgent();
  const revokeMutation = useRevokeUserAgent();
  const assignedNames = assignments?.agent_names ?? [];
  const pageStart = total === 0 ? 0 : userOffset + 1;
  const pageEnd = Math.min(userOffset + users.length, total);
  const canPreviousPage = pageIndex > 0;
  const canNextPage = pageEnd < total;

  useEffect(() => {
    if (isUsersLoading) return;
    const firstUser = users[0];
    if (!firstUser) {
      setActiveUserId(null);
      return;
    }
    if (!activeUserId || !users.some((user) => user.id === activeUserId)) {
      setActiveUserId(firstUser.id);
    }
  }, [activeUserId, isUsersLoading, users]);

  useEffect(() => {
    const firstAgent = validAgents[0];
    if (!firstAgent) {
      if (selectedAgent) setSelectedAgent("");
      return;
    }
    if (!validAgents.some((agent) => agent.name === selectedAgent)) {
      setSelectedAgent(firstAgent.name);
    }
  }, [selectedAgent, validAgents]);

  async function grantSelectedAgent() {
    if (!selectedUserId || !selectedAgent) return;
    try {
      await grantMutation.mutateAsync({
        userId: selectedUserId,
        agentName: selectedAgent,
      });
      toast.success("Agent granted");
    } catch (err) {
      toast.error(displayError(err));
    }
  }

  async function revokeAgent(agentName: string) {
    if (!selectedUserId) return;
    try {
      await revokeMutation.mutateAsync({ userId: selectedUserId, agentName });
      toast.success("Agent revoked");
    } catch (err) {
      toast.error(displayError(err));
    }
  }

  function movePage(nextPageIndex: number) {
    setPageIndex(nextPageIndex);
    setActiveUserId(null);
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">User assignments</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          Grant file-backed agents to normal users.
        </p>
      </div>

      {usersError && (
        <Alert variant="destructive">
          <AlertCircleIcon />
          <AlertTitle>Users unavailable</AlertTitle>
          <AlertDescription>{displayError(usersError)}</AlertDescription>
        </Alert>
      )}

      {assignmentsError && (
        <Alert variant="destructive">
          <AlertCircleIcon />
          <AlertTitle>Assignments unavailable</AlertTitle>
          <AlertDescription>{displayError(assignmentsError)}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(360px,0.9fr)_minmax(0,1.4fr)]">
        <div className="rounded-md border">
          <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
            <div>
              <div className="text-sm font-medium">Users</div>
              <div className="text-muted-foreground mt-0.5 text-xs">
                {pageStart}-{pageEnd} of {total}
              </div>
            </div>
            <div className="flex items-center gap-1">
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-8 w-8"
                disabled={!canPreviousPage || isUsersLoading}
                onClick={() => movePage(pageIndex - 1)}
                title="Previous page"
              >
                <ChevronLeftIcon className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-8 w-8"
                disabled={!canNextPage || isUsersLoading}
                onClick={() => movePage(pageIndex + 1)}
                title="Next page"
              >
                <ChevronRightIcon className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr className="text-left">
                  <th className="px-4 py-3 font-medium">User</th>
                  <th className="w-28 px-4 py-3 font-medium">Role</th>
                  <th className="w-28 px-4 py-3 font-medium">Status</th>
                  <th className="w-24 px-4 py-3 font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {isUsersLoading ? (
                  <tr>
                    <td
                      className="text-muted-foreground px-4 py-8 text-center"
                      colSpan={4}
                    >
                      Loading...
                    </td>
                  </tr>
                ) : users.length === 0 ? (
                  <tr>
                    <td
                      className="text-muted-foreground px-4 py-8 text-center"
                      colSpan={4}
                    >
                      No users.
                    </td>
                  </tr>
                ) : (
                  users.map((user) => {
                    const isSelected = user.id === selectedUserId;
                    return (
                      <tr
                        key={user.id}
                        className={cn(
                          "border-t",
                          isSelected && "bg-muted/40",
                        )}
                      >
                        <td className="px-4 py-3">
                          <button
                            type="button"
                            className="block w-full min-w-0 text-left"
                            onClick={() => setActiveUserId(user.id)}
                          >
                            <div className="flex min-w-0 items-center gap-2">
                              {user.system_role === "admin" ? (
                                <ShieldIcon className="text-muted-foreground h-4 w-4 shrink-0" />
                              ) : (
                                <UserRoundIcon className="text-muted-foreground h-4 w-4 shrink-0" />
                              )}
                              <span className="truncate font-medium">
                                {user.email}
                              </span>
                            </div>
                            <div className="text-muted-foreground mt-1 break-all pl-6 font-mono text-xs">
                              {user.id}
                            </div>
                          </button>
                        </td>
                        <td className="px-4 py-3">
                          <Badge
                            variant={
                              user.system_role === "admin"
                                ? "default"
                                : "secondary"
                            }
                          >
                            {roleLabel(user.system_role)}
                          </Badge>
                        </td>
                        <td className="px-4 py-3">
                          <Badge
                            variant={user.needs_setup ? "outline" : "secondary"}
                          >
                            {user.needs_setup ? "Setup" : "Active"}
                          </Badge>
                        </td>
                        <td className="px-4 py-3">
                          <Button
                            type="button"
                            variant={isSelected ? "secondary" : "outline"}
                            size="sm"
                            disabled={isSelected}
                            onClick={() => setActiveUserId(user.id)}
                          >
                            {isSelected ? (
                              <>
                                <CheckIcon className="mr-1.5 h-4 w-4" />
                                Set
                              </>
                            ) : (
                              "Select"
                            )}
                          </Button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-md border p-4">
            <div className="text-sm font-medium">Selected user</div>
            {selectedUser ? (
              <div className="mt-3 min-w-0">
                <div className="truncate text-sm font-medium">
                  {selectedUser.email}
                </div>
                <div className="text-muted-foreground mt-1 break-all font-mono text-xs">
                  {selectedUser.id}
                </div>
              </div>
            ) : (
              <div className="text-muted-foreground mt-3 text-sm">
                No selected user.
              </div>
            )}
          </div>

          <div className="overflow-x-auto rounded-md border">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr className="text-left">
                  <th className="px-4 py-3 font-medium">Assigned agent</th>
                  <th className="px-4 py-3 font-medium">Capability</th>
                  <th className="w-24 px-4 py-3 font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {!selectedUserId ? (
                  <tr>
                    <td
                      className="text-muted-foreground px-4 py-8 text-center"
                      colSpan={3}
                    >
                      No selected user.
                    </td>
                  </tr>
                ) : isAssignmentsLoading ? (
                  <tr>
                    <td
                      className="text-muted-foreground px-4 py-8 text-center"
                      colSpan={3}
                    >
                      Loading...
                    </td>
                  </tr>
                ) : assignedNames.length === 0 ? (
                  <tr>
                    <td
                      className="text-muted-foreground px-4 py-8 text-center"
                      colSpan={3}
                    >
                      No assigned agents.
                    </td>
                  </tr>
                ) : (
                  assignedNames.map((agentName) => {
                    const entry = agents.find(
                      (agent) => agent.name === agentName,
                    );
                    return (
                      <tr key={agentName} className="border-t">
                        <td className="px-4 py-3">
                          <div className="font-medium">
                            {entry?.display_name ?? agentName}
                          </div>
                          <div className="text-muted-foreground mt-0.5 text-xs">
                            {agentName}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-1">
                            {(entry?.mcp_servers ?? [])
                              .slice(0, 3)
                              .map((server) => (
                                <Badge key={server} variant="outline">
                                  {server}
                                </Badge>
                              ))}
                            {(entry?.skills ?? []).slice(0, 3).map((skill) => (
                              <Badge key={skill} variant="secondary">
                                {skill}
                              </Badge>
                            ))}
                            {!entry && (
                              <span className="text-muted-foreground text-xs">
                                -
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="text-destructive hover:text-destructive h-8 w-8"
                            disabled={revokeMutation.isPending}
                            onClick={() => void revokeAgent(agentName)}
                            title="Revoke"
                          >
                            <Trash2Icon className="h-4 w-4" />
                          </Button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <div className="rounded-md border p-4">
            <div className="text-sm font-medium">Grant agent</div>
            <div className="mt-3 space-y-3">
              <label className="block">
                <span className="text-muted-foreground mb-1 block text-xs font-medium">
                  Agent
                </span>
                <select
                  value={selectedAgent}
                  onChange={(event) => setSelectedAgent(event.target.value)}
                  className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                >
                  {validAgents.length === 0 ? (
                    <option value="">No valid agents</option>
                  ) : (
                    validAgents.map((agent) => (
                      <option key={agent.name} value={agent.name}>
                        {agent.display_name ?? agent.name}
                      </option>
                    ))
                  )}
                </select>
              </label>
              <Button
                type="button"
                className="w-full"
                disabled={
                  !selectedUserId || !selectedAgent || grantMutation.isPending
                }
                onClick={() => void grantSelectedAgent()}
              >
                <PlusIcon className="mr-1.5 h-4 w-4" />
                Grant
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

import type { Agent } from "./types";

export function getAgentDisplayName(
  agent: Agent | null | undefined,
  fallbackName?: string,
): string {
  const displayName = agent?.display_name?.trim();
  if (displayName) {
    return displayName;
  }
  return agent?.name ?? fallbackName ?? "";
}

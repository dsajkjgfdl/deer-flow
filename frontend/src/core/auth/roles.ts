import type { User } from "./types";

type RoleUser = Pick<User, "system_role"> | null | undefined;

export function canAccessPlatformAdmin(user: RoleUser): boolean {
  return user?.system_role === "admin";
}

export function canManageCustomAgents(user: RoleUser): boolean {
  return user?.system_role === "admin";
}

import { expect, test } from "vitest";

import type { User } from "@/core/auth/types";

const admin: User = {
  id: "admin-1",
  email: "admin@example.com",
  system_role: "admin",
  needs_setup: false,
};

const normalUser: User = {
  id: "user-1",
  email: "user@example.com",
  system_role: "user",
  needs_setup: false,
};

test("only admin users can access the platform admin menu", async () => {
  const { canAccessPlatformAdmin } = await import("@/core/auth/roles");

  expect(canAccessPlatformAdmin(admin)).toBe(true);
  expect(canAccessPlatformAdmin(normalUser)).toBe(false);
  expect(canAccessPlatformAdmin(null)).toBe(false);
});

test("only admin users can manage custom agents", async () => {
  const { canManageCustomAgents } = await import("@/core/auth/roles");

  expect(canManageCustomAgents(admin)).toBe(true);
  expect(canManageCustomAgents(normalUser)).toBe(false);
  expect(canManageCustomAgents(undefined)).toBe(false);
});

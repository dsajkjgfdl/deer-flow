import { beforeEach, expect, test, vi } from "vitest";

const fetchWithAuth = vi.fn();

vi.mock("@/core/api/fetcher", () => ({
  fetch: fetchWithAuth,
}));

beforeEach(() => {
  fetchWithAuth.mockReset();
});

test("listAgents loads only platform-runnable agents", async () => {
  fetchWithAuth.mockResolvedValue({
    ok: true,
    json: async () => ({
      agents: [
        {
          name: "hr-boss-agent",
          display_name: "HR Boss",
          description: "assigned",
          model: "qwen3.5-plus",
          tool_groups: [],
          skills: ["hr-boss"],
          mcp_servers: ["text2cypher"],
          status: "valid",
          validation_errors: [],
          validation_warnings: [],
        },
      ],
    }),
  });

  const { listAgents } = await import("@/core/agents/api");

  await expect(listAgents()).resolves.toMatchObject([
    { name: "hr-boss-agent", display_name: "HR Boss" },
  ]);
  expect(fetchWithAuth).toHaveBeenCalledWith(
    expect.stringContaining("/api/platform/agents"),
  );
});

test("getAgent checks assignment through the platform endpoint", async () => {
  fetchWithAuth.mockResolvedValue({
    ok: true,
    json: async () => ({
      name: "hr-boss-agent",
      display_name: "HR Boss",
      description: "assigned",
      model: "qwen3.5-plus",
      tool_groups: [],
      skills: ["hr-boss"],
      mcp_servers: ["text2cypher"],
      status: "valid",
      validation_errors: [],
      validation_warnings: [],
    }),
  });

  const { getAgent } = await import("@/core/agents/api");

  await expect(getAgent("hr-boss-agent")).resolves.toMatchObject({
    name: "hr-boss-agent",
  });
  expect(fetchWithAuth).toHaveBeenCalledWith(
    expect.stringContaining("/api/platform/agents/hr-boss-agent"),
  );
});

import { beforeEach, expect, test, vi } from "vitest";

const fetchWithAuth = vi.fn();

vi.mock("@/core/api/fetcher", () => ({
  fetch: fetchWithAuth,
}));

beforeEach(() => {
  fetchWithAuth.mockReset();
});

test("listPlatformUsers requests a paginated admin user page", async () => {
  fetchWithAuth.mockResolvedValue({
    ok: true,
    json: async () => ({
      items: [
        {
          id: "user-1",
          email: "alice@example.com",
          system_role: "user",
          needs_setup: false,
          created_at: "2026-05-29T00:00:00+00:00",
        },
      ],
      total: 12,
      limit: 10,
      offset: 20,
    }),
  });

  const { listPlatformUsers } = await import("@/core/platform/api");

  await expect(
    listPlatformUsers({ limit: 10, offset: 20 }),
  ).resolves.toMatchObject({
    total: 12,
    limit: 10,
    offset: 20,
    items: [{ email: "alice@example.com" }],
  });

  expect(fetchWithAuth).toHaveBeenCalledWith(
    expect.stringContaining("/api/platform/admin/users?limit=10&offset=20"),
  );
});

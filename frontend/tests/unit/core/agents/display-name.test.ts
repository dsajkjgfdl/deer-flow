import { expect, test } from "vitest";

import { getAgentDisplayName } from "@/core/agents/utils";

test("prefers display_name over internal name", () => {
  expect(
    getAgentDisplayName({
      name: "hr-boss-agent",
      display_name: "人岗匹配智能体",
      description: "",
      model: null,
      tool_groups: null,
      skills: null,
    }),
  ).toBe("人岗匹配智能体");
});

test("falls back to internal name when display_name is blank", () => {
  expect(
    getAgentDisplayName({
      name: "hr-boss-agent",
      display_name: "   ",
      description: "",
      model: null,
      tool_groups: null,
      skills: null,
    }),
  ).toBe("hr-boss-agent");
});

test("uses explicit fallback when agent is unavailable", () => {
  expect(getAgentDisplayName(null, "hr-boss-agent")).toBe("hr-boss-agent");
});

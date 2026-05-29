import { expect, test } from "vitest";

import { threadRunsQueryKey } from "@/core/threads/hooks";

test("threadRunsQueryKey scopes run history to the thread", () => {
  expect(threadRunsQueryKey("thread-1")).toEqual(["thread", "thread-1"]);
});

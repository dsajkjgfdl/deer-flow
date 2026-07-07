import type { FeedbackRecord } from "./types";

export interface NegativeFeedbackUserGroup {
  userKey: string;
  userLabel: string;
  count: number;
  commentCount: number;
  latestCreatedAt?: string;
  agentNames: string[];
  sourceChannels: string[];
  items: FeedbackRecord[];
}

export function groupNegativeFeedbackByUser(
  items: FeedbackRecord[],
): NegativeFeedbackUserGroup[] {
  const groups = new Map<string, NegativeFeedbackUserGroup>();

  for (const item of items) {
    if (item.rating !== -1) {
      continue;
    }

    const identity = feedbackUserIdentity(item);
    const group = groups.get(identity.key) ?? {
      userKey: identity.key,
      userLabel: identity.label,
      count: 0,
      commentCount: 0,
      latestCreatedAt: undefined,
      agentNames: [],
      sourceChannels: [],
      items: [],
    };

    group.count += 1;
    if (item.comment?.trim()) {
      group.commentCount += 1;
    }
    group.latestCreatedAt = latestTimeText(
      group.latestCreatedAt,
      item.created_at,
    );
    group.items.push(item);
    group.agentNames = sortedUnique([...group.agentNames, item.agent_name]);
    group.sourceChannels = sortedUnique([
      ...group.sourceChannels,
      channelName(item),
    ]);
    groups.set(identity.key, group);
  }

  return Array.from(groups.values())
    .map((group) => ({
      ...group,
      items: [...group.items].sort((a, b) =>
        compareCreatedAtDesc(a.created_at, b.created_at),
      ),
    }))
    .sort((a, b) => {
      if (a.count !== b.count) {
        return b.count - a.count;
      }
      const latestCompare = compareCreatedAtDesc(
        a.latestCreatedAt,
        b.latestCreatedAt,
      );
      if (latestCompare !== 0) {
        return latestCompare;
      }
      return a.userLabel.localeCompare(b.userLabel);
    });
}

function feedbackUserIdentity(item: FeedbackRecord) {
  const channel = channelName(item);
  if (channel !== "web") {
    const id =
      clean(item.platform_user_id) ??
      clean(item.user_id) ??
      clean(item.platform_chat_id) ??
      "unknown";
    return {
      key: `${channel}:${id}`,
      label: id === "unknown" ? "Unknown user" : id,
    };
  }

  const id =
    clean(item.user_email) ??
    clean(item.user_id) ??
    clean(item.run_user_id) ??
    "unknown";
  return {
    key: `web:${id}`,
    label: id === "unknown" ? "Unknown user" : id,
  };
}

function channelName(item: FeedbackRecord) {
  return clean(item.source_channel) ?? "web";
}

function clean(value: string | null | undefined) {
  const text = value?.trim();
  if (text === undefined || text.length === 0) {
    return undefined;
  }
  return text;
}

function latestTimeText(current: string | undefined, next: string | undefined) {
  if (!current) {
    return next;
  }
  if (!next) {
    return current;
  }
  return compareCreatedAtDesc(current, next) <= 0 ? current : next;
}

function compareCreatedAtDesc(
  left: string | null | undefined,
  right: string | null | undefined,
) {
  return timestamp(right) - timestamp(left);
}

function timestamp(value: string | null | undefined) {
  if (!value) {
    return 0;
  }
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? 0 : time;
}

function sortedUnique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) =>
    a.localeCompare(b),
  );
}

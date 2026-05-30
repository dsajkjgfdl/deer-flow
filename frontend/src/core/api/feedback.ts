import { getBackendBaseURL } from "../config";
import { buildFeedbackPayload } from "../messages/feedback";

import { fetch } from "./fetcher";

export interface FeedbackData {
  feedback_id: string;
  run_id?: string;
  thread_id?: string;
  user_id?: string | null;
  rating: number;
  comment: string | null;
  created_at?: string;
}

export async function upsertFeedback(
  threadId: string,
  runId: string,
  rating: number,
  comment?: string,
): Promise<FeedbackData> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/threads/${encodeURIComponent(threadId)}/runs/${encodeURIComponent(runId)}/feedback`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildFeedbackPayload(rating, comment)),
    },
  );
  if (!res.ok) {
    throw new Error(`Failed to submit feedback: ${res.status}`);
  }
  return res.json();
}

export async function deleteFeedback(
  threadId: string,
  runId: string,
): Promise<void> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/threads/${encodeURIComponent(threadId)}/runs/${encodeURIComponent(runId)}/feedback`,
    { method: "DELETE" },
  );
  if (!res.ok && res.status !== 404) {
    throw new Error(`Failed to delete feedback: ${res.status}`);
  }
}

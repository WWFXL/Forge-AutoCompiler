import type { AgentThread, AgentThreadState } from "./types";

export function selectThreadSnapshotValues(
  threadId: string | null | undefined,
  snapshot: AgentThread | null | undefined,
): AgentThreadState | null {
  if (!threadId || snapshot?.thread_id !== threadId) {
    return null;
  }
  return snapshot.values;
}

import type { CompileLog, CompileSessionSnapshot } from "../compile/types";

export interface CompileSessionEvidence {
  session: CompileSessionSnapshot;
  command_logs: Record<string, CompileLog>;
  replay_logs: Record<string, CompileLog>;
  replay_verification_logs: Record<string, CompileLog>;
}

export async function loadCompileEvidence(
  baseURL: string,
  threadId: string,
  sessionIds: string[],
): Promise<CompileSessionEvidence[]> {
  async function read<T>(path: string): Promise<T> {
    const response = await fetch(`${baseURL}${path}`, { cache: "no-store" });
    if (!response.ok)
      throw new Error(`编译证据请求失败：${path} (HTTP ${response.status})`);
    return (await response.json()) as T;
  }

  const sessions: CompileSessionEvidence[] = [];
  for (const sessionId of sessionIds) {
    const root = `/api/threads/${encodeURIComponent(threadId)}/compile-sessions/${encodeURIComponent(sessionId)}`;
    const session = await read<CompileSessionSnapshot>(root);
    const evidence: CompileSessionEvidence = {
      session,
      command_logs: Object.create(null) as Record<string, CompileLog>,
      replay_logs: Object.create(null) as Record<string, CompileLog>,
      replay_verification_logs: Object.create(null) as Record<
        string,
        CompileLog
      >,
    };

    const jobs: Array<() => Promise<void>> = [];
    for (const command of session.commands) {
      if (command.has_log) {
        jobs.push(async () => {
          evidence.command_logs[command.command_id] = await read<CompileLog>(
            `${root}/commands/${encodeURIComponent(command.command_id)}/log`,
          );
        });
      }
    }
    for (const attempt of session.replay_attempts) {
      if (attempt.has_log) {
        jobs.push(async () => {
          evidence.replay_logs[attempt.attempt_id] = await read<CompileLog>(
            `${root}/replays/${encodeURIComponent(attempt.attempt_id)}/log`,
          );
        });
      }
      if (attempt.has_verification_log) {
        jobs.push(async () => {
          evidence.replay_verification_logs[attempt.attempt_id] =
            await read<CompileLog>(
              `${root}/replays/${encodeURIComponent(attempt.attempt_id)}/verification-log`,
            );
        });
      }
    }

    let next = 0;
    await Promise.all(
      Array.from({ length: Math.min(4, jobs.length) }, async () => {
        while (next < jobs.length) {
          const job = jobs[next++];
          await job?.();
        }
      }),
    );
    sessions.push(evidence);
  }
  return sessions;
}

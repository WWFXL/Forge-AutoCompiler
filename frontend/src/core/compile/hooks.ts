import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { getBackendBaseURL } from "@/core/config";

import type { CompileLog, CompileSessionSnapshot } from "./types";

async function readEvidence<T>(path: string): Promise<T> {
  const response = await fetch(`${getBackendBaseURL()}${path}`, {
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Evidence HTTP ${response.status}`);
  return (await response.json()) as T;
}

function sessionPath(threadId: string, sessionId: string) {
  return `/api/threads/${encodeURIComponent(threadId)}/compile-sessions/${encodeURIComponent(sessionId)}`;
}

export function useCompileSession(
  threadId: string,
  sessionId: string | undefined,
  active: boolean,
) {
  const query = useQuery({
    queryKey: ["compile-session", threadId, sessionId],
    queryFn: () =>
      readEvidence<CompileSessionSnapshot>(sessionPath(threadId, sessionId!)),
    enabled: Boolean(sessionId),
    retry: false,
    refetchInterval: active ? 2000 : false,
  });
  const { refetch } = query;
  const wasActive = useRef(active);
  useEffect(() => {
    if (sessionId && wasActive.current && !active) void refetch();
    wasActive.current = active;
  }, [active, refetch, sessionId]);
  return query;
}

export function useCompileLog(
  threadId: string,
  sessionId: string,
  kind: "commands" | "replays" | "replay-verifications",
  recordId: string,
  enabled: boolean,
  active: boolean,
) {
  const query = useQuery({
    queryKey: ["compile-log", threadId, sessionId, kind, recordId],
    queryFn: () =>
      readEvidence<CompileLog>(
        kind === "replay-verifications"
          ? `${sessionPath(threadId, sessionId)}/replays/${encodeURIComponent(recordId)}/verification-log`
          : `${sessionPath(threadId, sessionId)}/${kind}/${encodeURIComponent(recordId)}/log`,
      ),
    enabled,
    retry: false,
    refetchInterval: enabled && active ? 2000 : false,
  });
  const { refetch } = query;
  const wasActive = useRef(active);
  useEffect(() => {
    if (enabled && wasActive.current && !active) void refetch();
    wasActive.current = active;
  }, [active, enabled, refetch]);
  return query;
}

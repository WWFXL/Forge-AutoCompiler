import { CheckCircleIcon, Loader2Icon, XCircleIcon } from "lucide-react";
import { useState } from "react";

import { useCompileLog, useCompileSession } from "@/core/compile/hooks";
import type { CompileCheck } from "@/core/compile/types";
import { useI18n } from "@/core/i18n/hooks";

function Checks({ checks }: { checks: CompileCheck[] }) {
  return (
    <ul className="space-y-1">
      {checks.map((check, index) => (
        <li
          key={`${check.name}-${index}`}
          className="flex items-start gap-2 text-xs"
        >
          {check.passed ? (
            <CheckCircleIcon className="mt-0.5 size-3 shrink-0 text-green-600 dark:text-green-400" />
          ) : (
            <XCircleIcon className="mt-0.5 size-3 shrink-0 text-red-600 dark:text-red-400" />
          )}
          <span className="min-w-0 break-words">
            {check.name}
            {check.summary ? `: ${check.summary}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

function EvidenceLog({
  threadId,
  sessionId,
  kind,
  recordId,
  active,
  label,
}: {
  threadId: string;
  sessionId: string;
  kind: "commands" | "replays" | "replay-verifications";
  recordId: string;
  active: boolean;
  label?: string;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const log = useCompileLog(threadId, sessionId, kind, recordId, open, active);
  return (
    <details
      className="mt-2 min-w-0"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="cursor-pointer text-xs">
        {label ?? t.compileTrace.log}
      </summary>
      {open && (
        <div className="mt-2">
          {log.isPending && (
            <span className="text-muted-foreground text-xs">
              {t.compileTrace.loading}
            </span>
          )}
          {log.isError && (
            <span className="text-destructive text-xs">
              {log.data
                ? t.compileTrace.refreshFailed
                : t.compileTrace.unavailable}
            </span>
          )}
          {log.data && (
            <>
              {log.data.truncated && (
                <p className="text-muted-foreground mb-1 text-xs">
                  {t.compileTrace.truncated}
                </p>
              )}
              <pre className="bg-muted text-foreground max-h-64 max-w-full overflow-auto rounded-md p-2 text-xs break-all whitespace-pre-wrap">
                <code>{log.data.output || t.compileTrace.emptyLog}</code>
              </pre>
            </>
          )}
        </div>
      )}
    </details>
  );
}

export function CompileSessionTrace({
  threadId,
  sessionId,
  active,
}: {
  threadId: string;
  sessionId?: string;
  active: boolean;
}) {
  const { t } = useI18n();
  const query = useCompileSession(threadId, sessionId, active);
  if (!sessionId)
    return (
      <p className="text-muted-foreground text-xs">
        {t.compileTrace.noSession}
      </p>
    );
  if (query.isPending)
    return (
      <p className="text-muted-foreground flex items-center gap-2 text-xs">
        <Loader2Icon className="size-3 animate-spin" />
        {t.compileTrace.loading}
      </p>
    );
  if (!query.data)
    return (
      <p className="text-destructive text-xs" role="status">
        {t.compileTrace.unavailable}
      </p>
    );
  const session = query.data;
  const compiledArtifacts = session.artifacts.filter(
    (artifact) => artifact.artifact_type !== "support_file",
  );
  const supportFiles = session.artifacts.filter(
    (artifact) => artifact.artifact_type === "support_file",
  );
  return (
    <section
      className="text-foreground min-w-0 space-y-3"
      aria-label={t.compileTrace.title}
      data-testid="compile-trace"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <strong>{t.compileTrace.title}</strong>
        <span>
          {t.compileTrace.session}: <code>{session.session_id}</code>
        </span>
        <span>
          {t.compileTrace.status}: {session.status}
        </span>
      </div>
      {query.isError && (
        <p className="text-destructive text-xs">
          {t.compileTrace.refreshFailed}
        </p>
      )}
      <div className="text-muted-foreground space-y-1 text-xs break-all">
        {session.repo_url && <p>{session.repo_url}</p>}
        {session.commit_sha && (
          <p>
            commit: <code>{session.commit_sha}</code>
          </p>
        )}
        {(session.executed_build_system ?? session.selected_build_system) && (
          <p>
            {t.compileTrace.buildSystem}:{" "}
            {session.executed_build_system ?? session.selected_build_system}
          </p>
        )}
      </div>
      <h4 className="text-xs font-semibold">
        {t.compileTrace.commands} ({session.commands.length})
      </h4>
      {session.commands.length === 0 && (
        <p className="text-muted-foreground text-xs">
          {t.compileTrace.noCommands}
        </p>
      )}
      <ol className="space-y-2">
        {session.commands.map((command, index) => (
          <li key={command.command_id} className="min-w-0 border-l-2 pl-3">
            <details>
              <summary className="cursor-pointer text-xs break-words">
                {index + 1}. {command.role || command.stage} ·{" "}
                {command.termination === "policy_rejected"
                  ? t.compileTrace.policyRejected
                  : `${t.compileTrace.exitCode}: ${command.exit_code ?? "—"}`}
                {command.termination === "policy_rejected" &&
                  command.exit_code != null &&
                  ` (${t.compileTrace.exitCode}: ${command.exit_code})`}
                {command.duration_seconds != null &&
                  ` · ${command.duration_seconds.toFixed(2)}s`}
                {command.timed_out && ` · ${t.compileTrace.timedOut}`}
              </summary>
              <p className="text-muted-foreground mt-2 text-xs break-all">
                cwd: <code>{command.workdir}</code>
              </p>
              <pre className="bg-muted text-foreground mt-1 max-h-64 max-w-full overflow-auto rounded-md p-2 text-xs break-all whitespace-pre-wrap">
                <code>{command.command}</code>
              </pre>
              {command.has_log && (
                <EvidenceLog
                  threadId={threadId}
                  sessionId={sessionId}
                  kind="commands"
                  recordId={command.command_id}
                  active={active}
                />
              )}
            </details>
          </li>
        ))}
      </ol>
      {session.artifacts.length > 0 && (
        <div className="min-w-0 space-y-2" data-testid="compile-artifacts">
          <h4 className="text-xs font-semibold">
            {t.compileTrace.artifacts} ({session.artifacts.length})
          </h4>
          <div className="space-y-1 text-xs">
            <p className="font-medium">
              {t.compileTrace.compiledArtifacts}: {compiledArtifacts.length}
            </p>
            <ul className="space-y-1 pl-3">
              {compiledArtifacts.map((artifact) => (
                <li
                  key={`${artifact.display_path}-${artifact.sha256}`}
                  className="min-w-0 break-words"
                >
                  <code>{artifact.display_path}</code>
                  <span className="text-muted-foreground">
                    {` · ${artifact.artifact_type}`}
                    {artifact.size_bytes != null &&
                      ` · ${artifact.size_bytes} B`}
                  </span>
                  {artifact.sha256 && (
                    <span className="text-muted-foreground block break-all">
                      {t.compileTrace.sha256}: {artifact.sha256}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
          {supportFiles.length > 0 && (
            <details className="min-w-0" data-testid="compile-support-files">
              <summary className="cursor-pointer text-xs font-medium break-words">
                {t.compileTrace.supportFiles}: {supportFiles.length}{" "}
                {t.compileTrace.files}
              </summary>
              <ul className="mt-2 space-y-2 pl-3 text-xs">
                {supportFiles.map((artifact) => (
                  <li
                    key={`${artifact.display_path}-${artifact.sha256}`}
                    className="min-w-0 break-words"
                  >
                    <code>{artifact.display_path}</code>
                    <span className="text-muted-foreground">
                      {artifact.size_bytes != null &&
                        ` · ${artifact.size_bytes} B`}
                    </span>
                    {artifact.sha256 && (
                      <span className="text-muted-foreground block break-all">
                        {t.compileTrace.sha256}: {artifact.sha256}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
      {session.verification && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold">
            {t.compileTrace.verification}: {session.verification.status}
          </h4>
          <Checks checks={session.verification.checks} />
        </div>
      )}
      <h4 className="text-xs font-semibold">
        {t.compileTrace.replays} ({session.replay_attempts.length})
      </h4>
      <ol className="space-y-3">
        {session.replay_attempts.map((attempt, index) => (
          <li
            key={attempt.attempt_id}
            className="min-w-0 space-y-2 border-l-2 pl-3"
          >
            <p className="text-xs break-all">
              {index + 1}. {attempt.status} · <code>{attempt.attempt_id}</code>
            </p>
            {attempt.failure_classification && (
              <p className="text-destructive text-xs break-words">
                {attempt.failure_classification}
              </p>
            )}
            <p className="text-muted-foreground text-xs">
              {t.compileTrace.cleanup}:{" "}
              {attempt.cleanup_succeeded === true
                ? t.compileTrace.passed
                : attempt.cleanup_succeeded === false
                  ? t.compileTrace.failed
                  : "—"}
            </p>
            <Checks checks={attempt.checks} />
            {attempt.has_log && (
              <EvidenceLog
                threadId={threadId}
                sessionId={sessionId}
                kind="replays"
                recordId={attempt.attempt_id}
                active={active}
              />
            )}
            {attempt.has_verification_log && (
              <EvidenceLog
                threadId={threadId}
                sessionId={sessionId}
                kind="replay-verifications"
                recordId={attempt.attempt_id}
                active={active}
                label={`${t.compileTrace.verification} ${t.compileTrace.log}`}
              />
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

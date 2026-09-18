export interface CompileCheck {
  name: string;
  passed: boolean;
  exit_code: number | null;
  summary: string | null;
}

export interface CompileCommand {
  command_id: string;
  stage: string;
  role: string;
  command: string;
  workdir: string;
  exit_code: number | null;
  duration_seconds: number | null;
  timed_out: boolean;
  has_log: boolean;
}

export interface CompileReplay {
  attempt_id: string;
  status: string;
  duration_seconds: number | null;
  failure_classification: string | null;
  cleanup_succeeded: boolean | null;
  checks: CompileCheck[];
  has_log: boolean;
}

export interface CompileSessionSnapshot {
  session_id: string;
  status: string;
  repo_url: string | null;
  commit_sha: string | null;
  selected_build_system: string | null;
  executed_build_system: string | null;
  commands: CompileCommand[];
  verification: { status: string; checks: CompileCheck[] } | null;
  replay_attempts: CompileReplay[];
}

export interface CompileLog {
  output: string;
  truncated: boolean;
}

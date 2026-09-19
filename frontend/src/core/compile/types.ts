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
  termination: string | null;
  has_log: boolean;
}

export interface CompileArtifact {
  path: string;
  display_path: string;
  artifact_type: string;
  size_bytes: number | null;
  sha256: string | null;
}

export interface CompileReplay {
  attempt_id: string;
  status: string;
  duration_seconds: number | null;
  failure_classification: string | null;
  cleanup_succeeded: boolean | null;
  verification_exit_code: number | null;
  checks: CompileCheck[];
  has_log: boolean;
  has_verification_log: boolean;
}

export interface CompileSessionSnapshot {
  session_id: string;
  status: string;
  repo_url: string | null;
  commit_sha: string | null;
  selected_build_system: string | null;
  executed_build_system: string | null;
  parallel_jobs: number;
  commands: CompileCommand[];
  artifacts: CompileArtifact[];
  verification: { status: string; checks: CompileCheck[] } | null;
  replay_attempts: CompileReplay[];
}

export interface CompileLog {
  output: string;
  truncated: boolean;
}

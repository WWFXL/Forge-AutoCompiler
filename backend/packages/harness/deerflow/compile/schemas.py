from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BuildCommandRecord:
    stage: str
    command: str
    workdir: str
    started_at: str = field(default_factory=utc_now_iso)
    completed_at: str | None = None
    exit_code: int | None = None
    log_path: str | None = None


@dataclass
class BuildArtifact:
    path: str
    artifact_type: str
    size_bytes: int | None = None
    source_path: str | None = None


@dataclass
class VerificationCheck:
    name: str
    target: str
    command: str
    passed: bool
    exit_code: int | None = None
    log_path: str | None = None
    summary: str | None = None


@dataclass
class VerificationResult:
    status: str
    checks: list[VerificationCheck] = field(default_factory=list)
    artifact_count: int = 0
    failed_checks: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    combined_output: str
    log_path: str | None = None


@dataclass
class CompileSession:
    session_id: str
    thread_id: str
    repo_url: str
    branch: str | None
    image: str
    status: str
    created_at: str = field(default_factory=utc_now_iso)
    completed_at: str | None = None
    task_id: str | None = None
    owner_subagent_id: str | None = None
    commit_sha: str | None = None
    container_id: str | None = None
    container_name: str | None = None
    build_system: str | None = None
    summary: str | None = None
    error: str | None = None
    host_session_dir: str = ""
    host_workspace_dir: str = ""
    host_artifacts_dir: str = ""
    host_logs_dir: str = ""
    host_repro_dir: str = ""
    metadata_path: str = ""
    container_workspace_dir: str = "/workspace"
    container_repo_dir: str = "/workspace/repo"
    container_artifacts_dir: str = "/artifacts"
    container_logs_dir: str = "/logs"
    container_repro_dir: str = "/repro"
    commands: list[BuildCommandRecord] = field(default_factory=list)
    artifacts: list[BuildArtifact] = field(default_factory=list)
    verification: VerificationResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompileSession":
        commands = [BuildCommandRecord(**item) for item in data.get("commands", [])]
        artifacts = [BuildArtifact(**item) for item in data.get("artifacts", [])]
        verification_data = data.get("verification")
        verification = None
        if verification_data:
            checks = [VerificationCheck(**item) for item in verification_data.get("checks", [])]
            verification_payload = {k: v for k, v in verification_data.items() if k != "checks"}
            verification = VerificationResult(checks=checks, **verification_payload)
        payload = {k: v for k, v in data.items() if k not in {"commands", "artifacts", "verification"}}
        return cls(commands=commands, artifacts=artifacts, verification=verification, **payload)

    @property
    def metadata_file(self) -> Path:
        return Path(self.metadata_path)

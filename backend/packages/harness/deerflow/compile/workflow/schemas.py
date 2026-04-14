from __future__ import annotations

from dataclasses import dataclass, field

from deerflow.compile.schemas import BuildArtifact, BuildCommandRecord


@dataclass
class CompileWorkflowInput:
    repo_url: str
    thread_id: str
    branch: str | None = None
    task_description: str | None = None
    artifact_hint: str | None = None
    build_goal: str | None = None
    max_build_attempts: int = 4
    owner_id: str | None = None
    generate_repro_bundle: bool = True


@dataclass
class BuildAttempt:
    stage: str
    command: str
    exit_code: int | None = None
    summary: str | None = None
    log_path: str | None = None

    @classmethod
    def from_command_record(cls, record: BuildCommandRecord, summary: str | None = None) -> "BuildAttempt":
        return cls(
            stage=record.stage,
            command=record.command,
            exit_code=record.exit_code,
            summary=summary,
            log_path=record.log_path,
        )


@dataclass
class CompileWorkflowState:
    thread_id: str
    repo_url: str
    branch: str | None = None
    task_description: str | None = None
    artifact_hint: str | None = None
    build_goal: str | None = None
    owner_id: str | None = None
    session_id: str | None = None
    build_system: str | None = None
    status: str = "pending"
    error: str | None = None
    summary: str | None = None
    prepare_done: bool = False
    clone_done: bool = False
    inspect_done: bool = False
    build_done: bool = False
    verify_done: bool = False
    finalized: bool = False
    attempts: list[BuildAttempt] = field(default_factory=list)
    artifacts: list[BuildArtifact] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    repro_files: list[str] = field(default_factory=list)


@dataclass
class CompileWorkflowResult:
    status: str
    summary: str
    session_id: str | None
    build_system: str | None
    attempts: list[BuildAttempt]
    artifacts: list[str]
    logs: list[str]
    repro_files: list[str]
    error: str | None = None


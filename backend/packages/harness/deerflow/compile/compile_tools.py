from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from deerflow.compile.operations import finalize_compile_session_impl, get_compile_services
from deerflow.compile.schemas import BuildCommandRecord, utc_now_iso


BuildSystemKind = Literal["cmake", "make", "autotools", "meson", "unknown"]
SessionFinalizationAction = Literal["suspend", "destroy"]
_BUILD_MARKERS: tuple[tuple[BuildSystemKind, str], ...] = (
    ("cmake", "CMakeLists.txt"),
    ("make", "Makefile"),
    ("autotools", "configure"),
    ("meson", "meson.build"),
)


@dataclass(frozen=True)
class PrepareWorkspaceInput:
    thread_id: str
    repo_url: str
    branch: str | None = None


@dataclass(frozen=True)
class PrepareWorkspaceResult:
    session_id: str
    container_id: str
    workspace_path: str
    lead_session_path: str
    lead_repo_path: str
    container_repo_path: str


@dataclass(frozen=True)
class IdentifyBuildSystemInput:
    thread_id: str
    session_id: str
    workspace_path: str


@dataclass(frozen=True)
class IdentifyBuildSystemResult:
    system: BuildSystemKind
    root_file: str | None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FinalizeSessionInput:
    thread_id: str
    session_id: str


@dataclass(frozen=True)
class FinalizeSessionResult:
    session_id: str
    status: str
    logs: dict[str, Any] = field(default_factory=dict)
    artifact_paths: list[str] = field(default_factory=list)
    repro_bundle_path: str | None = None
    lead_repro_bundle_path: str | None = None
    host_repro_bundle_path: str | None = None
    action: SessionFinalizationAction = "destroy"


class PrepareWorkspaceTool:
    """Prepare a clean compile workspace for a repository."""

    def _verify_container_repo_view(self, session, lead_repo_path: Path) -> None:
        services = get_compile_services()
        verification_log_path = services.manager.local_logs_dir(session) / "002_container_repo_check.log"
        verify_command = (
            "test -d /workspace/repo && "
            "test -e /workspace/repo/.git && "
            "pwd && "
            "ls -la /workspace && "
            "ls -la /workspace/repo"
        )
        started_at = utc_now_iso()
        result = services.runtime.exec(
            session,
            verify_command,
            workdir=session.container_workspace_dir,
            timeout_seconds=30,
            log_path=str(verification_log_path),
        )
        completed_at = utc_now_iso()
        services.manager.record_command(
            session,
            BuildCommandRecord(
                stage="container_repo_check",
                command=verify_command,
                workdir=session.container_workspace_dir,
                started_at=started_at,
                completed_at=completed_at,
                exit_code=result.exit_code,
                log_path=str(verification_log_path),
            ),
        )
        if result.exit_code != 0:
            services.manager.mark_session_status(session, "failed", error=result.combined_output[:4000])
            services.manager.log_event(
                session,
                "prepare_workspace.container_repo_check_failed",
                container_id=session.container_id,
                lead_repo_path=str(lead_repo_path),
                container_repo_path=session.container_repo_dir,
                log_path=str(verification_log_path),
                output=result.combined_output[:4000],
            )
            raise RuntimeError(
                "Workspace prepared on the lead side, but the compile container cannot see the same repository at "
                f"{session.container_repo_dir}. lead_repo_path={lead_repo_path}, log_path={verification_log_path}"
            )
        services.manager.log_event(
            session,
            "prepare_workspace.container_repo_check_completed",
            container_id=session.container_id,
            lead_repo_path=str(lead_repo_path),
            container_repo_path=session.container_repo_dir,
            log_path=str(verification_log_path),
        )

    def run(self, payload: PrepareWorkspaceInput) -> PrepareWorkspaceResult:
        services = get_compile_services()
        session = services.manager.create_session(thread_id=payload.thread_id, repo_url=payload.repo_url, branch=payload.branch)
        clone_log_path = services.manager.local_logs_dir(session) / "001_clone.log"
        session_dir = Path(session.metadata_path).parent
        workspace_dir = session_dir / "workspace"
        repo_dir = workspace_dir / "repo"

        try:
            services.runtime.create_container(session)
            services.manager.save_session(session)
            services.manager.log_event(
                session,
                "prepare_workspace.started",
                thread_id=payload.thread_id,
                repo_url=payload.repo_url,
                branch=payload.branch,
                container_id=session.container_id,
                workspace_path=session.container_repo_dir,
                lead_session_path=str(session_dir),
                lead_repo_path=str(repo_dir),
                clone_target=str(repo_dir),
            )

            if repo_dir.exists():
                shutil.rmtree(repo_dir)

            clone_command = ["git", "clone", "--depth", "1"]
            if payload.branch:
                clone_command.extend(["--branch", payload.branch])
            clone_command.extend([payload.repo_url, str(repo_dir)])

            started_at = utc_now_iso()
            result = subprocess.run(clone_command, capture_output=True, text=True)
            completed_at = utc_now_iso()
            combined_output = (result.stdout or "") + (result.stderr or "")
            clone_log_path.write_text(combined_output, encoding="utf-8")
            services.manager.record_command(
                session,
                BuildCommandRecord(
                    stage="clone",
                    command=" ".join(clone_command),
                    workdir=str(workspace_dir),
                    started_at=started_at,
                    completed_at=completed_at,
                    exit_code=result.returncode,
                    log_path=str(clone_log_path),
                ),
            )

            if result.returncode != 0:
                services.manager.mark_session_status(session, "failed", error=combined_output[:4000])
                services.manager.log_event(
                    session,
                    "prepare_workspace.failed",
                    thread_id=payload.thread_id,
                    container_id=session.container_id,
                    exit_code=result.returncode,
                    log_path=str(clone_log_path),
                    output=combined_output[:4000],
                )
                raise RuntimeError(f"Failed to clone repository: {combined_output.strip() or payload.repo_url}")

            head_result = subprocess.run(
                ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
            if head_result.returncode == 0:
                session.commit_sha = head_result.stdout.strip()

            self._verify_container_repo_view(session, repo_dir)

            session.summary = f"Workspace prepared for {payload.repo_url}"
            services.manager.save_session(session)
            services.manager.mark_session_status(session, "source_ready", summary=session.summary)
            services.manager.log_event(
                session,
                "prepare_workspace.completed",
                thread_id=payload.thread_id,
                session_id=session.session_id,
                container_id=session.container_id,
                workspace_path=session.container_repo_dir,
                lead_session_path=str(session_dir),
                lead_repo_path=str(repo_dir),
                commit_sha=session.commit_sha,
                log_path=str(clone_log_path),
            )
            return PrepareWorkspaceResult(
                session_id=session.session_id,
                container_id=session.container_id or "",
                workspace_path=str(workspace_dir),
                lead_session_path=str(session_dir),
                lead_repo_path=str(repo_dir),
                container_repo_path=session.container_repo_dir,
            )
        except Exception:
            if session.container_id:
                services.runtime.stop_and_remove_container(session)
            raise


class IdentifyBuildSystemTool:
    """Identify the repository build system inside the compile container."""

    def run(self, payload: IdentifyBuildSystemInput) -> IdentifyBuildSystemResult:
        services = get_compile_services()
        session = services.manager.load_session(payload.session_id, payload.thread_id)
        repo_root = session.container_repo_dir

        for system, marker in _BUILD_MARKERS:
            marker_path = f"{repo_root}/{marker}"
            check_command = f"test -f {marker_path}"
            result = services.runtime.exec(session, check_command, workdir=session.container_workspace_dir)
            if result.exit_code == 0:
                session.build_system = system
                services.manager.save_session(session)
                services.manager.log_event(
                    session,
                    "identify_build_system.completed",
                    thread_id=payload.thread_id,
                    container_id=session.container_id,
                    system=system,
                    root_file=marker,
                    workspace_path=repo_root,
                )
                return IdentifyBuildSystemResult(
                    system=system,
                    root_file=marker,
                    details={
                        "thread_id": payload.thread_id,
                        "session_id": payload.session_id,
                        "container_id": session.container_id,
                        "workspace_path": repo_root,
                        "lead_repo_path": repo_root,
                        "container_repo_path": repo_root,
                        "root_file_path": marker_path,
                    },
                )

        session.build_system = "unknown"
        services.manager.save_session(session)
        services.manager.log_event(
            session,
            "identify_build_system.completed",
            thread_id=payload.thread_id,
            container_id=session.container_id,
            system="unknown",
            root_file=None,
            workspace_path=repo_root,
        )
        return IdentifyBuildSystemResult(
            system="unknown",
            root_file=None,
            details={
                "thread_id": payload.thread_id,
                "session_id": payload.session_id,
                "container_id": session.container_id,
                "workspace_path": repo_root,
                "lead_repo_path": repo_root,
                "container_repo_path": repo_root,
                "checked_markers": [marker for _, marker in _BUILD_MARKERS],
            },
        )


class FinalizeSessionTool:
    """Finalize a compile session and gather logs/artifacts."""

    def run(self, payload: FinalizeSessionInput) -> FinalizeSessionResult:
        services = get_compile_services()
        session = services.manager.load_session(payload.session_id, payload.thread_id)
        result = finalize_compile_session_impl(session=session)
        return FinalizeSessionResult(
            session_id=result.session_id,
            status=result.status,
            logs={
                "workflow_log": str(services.manager.workflow_log_path(result)),
            },
            artifact_paths=[artifact.path for artifact in result.artifacts],
            repro_bundle_path=None,
            lead_repro_bundle_path=None,
            host_repro_bundle_path=None,
            action="destroy",
        )

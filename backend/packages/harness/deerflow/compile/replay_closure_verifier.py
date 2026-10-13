"""候选冻结前的 replay closure 验证。"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from deerflow.compile.agent_workflow_schemas import SubmitCandidateRequest
from deerflow.compile.candidate_verifier import DeliveryEntry, scan_delivery
from deerflow.compile.docker_runtime import ContainerCleanupResult, ReplayContainerHandle
from deerflow.compile.operations import _write_repro_bundle, build_replay_recipe, get_compile_services
from deerflow.compile.paths import get_replay_artifacts_dir, get_replay_attempt_dir, get_replay_logs_dir, get_replay_recipe_dir, get_replay_workspace_dir
from deerflow.compile.schemas import CompileSession

REPLAY_CLOSURE_SCHEMA_VERSION = "agent-workflow-replay-closure-v1"
_MAX_OUTPUT_CHARS = 2000


@dataclass(frozen=True)
class ReplayClosureVerificationResult:
    passed: bool
    classification: str
    frontier_sha256: str
    recipe_fingerprint: str | None
    exit_code: int | None
    cleanup_succeeded: bool
    expected_delivery: tuple[DeliveryEntry, ...]
    actual_delivery: tuple[DeliveryEntry, ...]
    output_excerpt: str
    duration_seconds: float
    schema_version: str = REPLAY_CLOSURE_SCHEMA_VERSION

    def canonical_payload(self) -> dict[str, object]:
        return asdict(self)

    def canonical_json(self) -> str:
        return json.dumps(self.canonical_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _delivery_payload(entries: tuple[DeliveryEntry, ...]) -> list[dict[str, object]]:
    return [asdict(entry) for entry in entries]


def replay_closure_frontier(
    *,
    session: CompileSession,
    request: SubmitCandidateRequest,
    recipe_fingerprint: str | None,
    delivery: tuple[DeliveryEntry, ...],
) -> str:
    payload = {
        "commit_sha": session.commit_sha,
        "image_id": session.image_id,
        "parallel_jobs": session.parallel_jobs,
        "replay_source_archive_sha256": session.replay_source_archive_sha256,
        "request_sha256": request.canonical_sha256(),
        "recipe_fingerprint": recipe_fingerprint,
        "delivery": _delivery_payload(delivery),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _classify_execution_failure(*, output: str, workspace_dir: Path, exit_code: int) -> str:
    if exit_code == 124:
        return "timeout"
    repo_dir = workspace_dir / "repo"
    bootstrap_input = any((repo_dir / name).is_file() for name in ("configure.ac", "configure.in"))
    configure_missing = not (repo_dir / "configure").exists()
    if bootstrap_input and configure_missing and re.search(r"(?:\./)?configure.*(?:No such file|not found)", output, re.IGNORECASE):
        return "missing_bootstrap_step"
    if re.search(r"No rule to make target\s+['`].+?['`]", output, re.IGNORECASE):
        return "missing_generated_input"
    return "recipe_execution_failed"


def _delivery_mismatch_classification(
    expected: tuple[DeliveryEntry, ...],
    actual: tuple[DeliveryEntry, ...],
) -> str | None:
    expected_paths = tuple(entry.relative_path for entry in expected)
    actual_paths = tuple(entry.relative_path for entry in actual)
    if expected_paths != actual_paths:
        return "artifact_set_mismatch"
    if expected != actual:
        return "artifact_content_mismatch"
    return None


class ReplayClosureVerifier:
    def __init__(self, *, timeout_seconds: int = 1200):
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds 必须大于 0")
        self.timeout_seconds = timeout_seconds

    def verify(
        self,
        *,
        request: SubmitCandidateRequest,
        session: CompileSession,
    ) -> ReplayClosureVerificationResult:
        started = time.monotonic()
        services = get_compile_services()
        current = services.manager.load_session(session.session_id, session.thread_id)
        expected_snapshot = scan_delivery(Path(current.leadagent_artifacts_dir))
        expected = expected_snapshot.entries
        recipe_fingerprint: str | None = None
        frontier = replay_closure_frontier(
            session=current,
            request=request,
            recipe_fingerprint=None,
            delivery=expected,
        )
        attempt_id = f"prefreeze-{uuid.uuid4().hex}"
        attempt_root = get_replay_attempt_dir(current.session_id, current.thread_id, attempt_id, services.manager.paths)
        recipe_dir = get_replay_recipe_dir(current.session_id, current.thread_id, attempt_id, services.manager.paths)
        workspace_dir = get_replay_workspace_dir(current.session_id, current.thread_id, attempt_id, services.manager.paths)
        artifacts_dir = get_replay_artifacts_dir(current.session_id, current.thread_id, attempt_id, services.manager.paths)
        logs_dir = get_replay_logs_dir(current.session_id, current.thread_id, attempt_id, services.manager.paths)
        handle: ReplayContainerHandle | None = None
        cleanup = ContainerCleanupResult(succeeded=True, stopped=True, removed=True)
        exit_code: int | None = None
        output = ""
        actual: tuple[DeliveryEntry, ...] = ()
        classification = "internal_error"
        passed = False
        mounted_content_cleanup_succeeded = True
        try:
            if expected_snapshot.invalid_paths:
                raise ValueError("Current delivery contains invalid paths")
            if len(request.supporting_command_ids) != 1:
                raise ValueError("Replay closure requires exactly one supporting build command")
            supporting_id = request.supporting_command_ids[0]
            supporting_position = next(index for index, command in enumerate(current.commands) if command.command_id == supporting_id)
            verification_ids = [command.command_id for command in current.commands[supporting_position + 1 :] if command.role == "smoke" and command.exit_code == 0 and not command.timed_out]
            recipe = build_replay_recipe(
                current,
                supporting_command_id=supporting_id,
                recipe_command_ids=list(request.recipe_command_ids),
                verification_command_ids=verification_ids,
            )
            recipe_fingerprint = recipe.fingerprint
            frontier = replay_closure_frontier(
                session=current,
                request=request,
                recipe_fingerprint=recipe_fingerprint,
                delivery=expected,
            )
            for directory in (recipe_dir, workspace_dir, artifacts_dir, logs_dir):
                directory.mkdir(parents=True, exist_ok=False)
            source_archive = Path(current.leadagent_repro_dir) / "source.tar" if current.replay_source_archive_sha256 else None
            _write_repro_bundle(
                current,
                recipe,
                repro_dir=recipe_dir,
                source_archive_path=source_archive,
            )
            current.replay_recipe = recipe
            handle = services.runtime.create_replay_container(
                current,
                attempt_id=attempt_id,
                timeout_seconds=min(30, self.timeout_seconds),
            )
            result = services.runtime.exec_replay_container(
                current,
                handle,
                timeout_seconds=self.timeout_seconds,
                log_path=str(logs_dir / "build.log"),
            )
            exit_code = result.exit_code
            output = result.combined_output
            if exit_code != 0:
                classification = _classify_execution_failure(
                    output=output,
                    workspace_dir=workspace_dir,
                    exit_code=exit_code,
                )
            else:
                if recipe.verification_steps:
                    verification = services.runtime.exec_replay_container(
                        current,
                        handle,
                        command="bash /repro/verify.sh",
                        timeout_seconds=self.timeout_seconds,
                        log_path=str(logs_dir / "verify.log"),
                    )
                    if verification.exit_code != 0:
                        exit_code = verification.exit_code
                        output = verification.combined_output
                        classification = "timeout" if verification.exit_code == 124 else "replay_verification_failed"
                        raise RuntimeError(classification)
                actual_snapshot = scan_delivery(artifacts_dir)
                actual = actual_snapshot.entries
                if actual_snapshot.invalid_paths:
                    classification = "artifact_set_mismatch"
                else:
                    mismatch = _delivery_mismatch_classification(expected, actual)
                    classification = mismatch or "passed"
                    passed = mismatch is None
        except subprocess.TimeoutExpired as exc:
            classification = "timeout"
            output = str(exc)
        except Exception as exc:
            if classification not in {"timeout", "replay_verification_failed"}:
                classification = "internal_error"
                output = f"{type(exc).__name__}: {exc}"
        finally:
            if handle is not None:
                try:
                    mounted_cleanup = services.runtime.exec_replay_container(
                        current,
                        handle,
                        command=("find /workspace /artifacts /logs -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +"),
                        workdir="/",
                        timeout_seconds=30,
                    )
                    mounted_content_cleanup_succeeded = mounted_cleanup.exit_code == 0
                    cleanup = services.runtime.stop_and_remove_replay_container(
                        current,
                        handle,
                        container_id=handle.container_id,
                        container_name=handle.container_name,
                    )
                except Exception as exc:
                    cleanup = ContainerCleanupResult(succeeded=False, stopped=False, removed=False)
                    mounted_content_cleanup_succeeded = False
                    output = f"{output}\ncleanup: {type(exc).__name__}: {exc}".strip()
            if not mounted_content_cleanup_succeeded or not cleanup.succeeded or not cleanup.removed:
                classification = "cleanup_failed"
                passed = False
            if cleanup.succeeded and cleanup.removed:
                shutil.rmtree(attempt_root, ignore_errors=True)
        return ReplayClosureVerificationResult(
            passed=passed,
            classification=classification,
            frontier_sha256=frontier,
            recipe_fingerprint=recipe_fingerprint,
            exit_code=exit_code,
            cleanup_succeeded=mounted_content_cleanup_succeeded and cleanup.succeeded and cleanup.removed,
            expected_delivery=expected,
            actual_delivery=actual,
            output_excerpt=output[-_MAX_OUTPUT_CHARS:],
            duration_seconds=round(time.monotonic() - started, 6),
        )


__all__ = [
    "REPLAY_CLOSURE_SCHEMA_VERSION",
    "ReplayClosureVerificationResult",
    "ReplayClosureVerifier",
    "replay_closure_frontier",
]

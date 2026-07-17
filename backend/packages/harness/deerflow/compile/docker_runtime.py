from __future__ import annotations

import math
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from deerflow.compile.paths import (
    get_host_artifacts_dir,
    get_host_logs_dir,
    get_host_replay_artifacts_dir,
    get_host_replay_logs_dir,
    get_host_replay_recipe_dir,
    get_host_replay_workspace_dir,
    get_host_repro_dir,
    get_host_session_dir,
    get_host_workspace_dir,
    get_replay_artifacts_dir,
    get_replay_logs_dir,
    get_replay_recipe_dir,
    get_replay_workspace_dir,
)
from deerflow.compile.schemas import CommandResult, CompileSession, utc_now_iso
from deerflow.config.paths import Paths

DEFAULT_NETWORK = "compile_network_wwf_v1"
CONTAINER_WORKSPACE_DIR = "/workspace"
CONTAINER_REPO_DIR = "/workspace/repo"
CONTAINER_ARTIFACTS_DIR = "/artifacts"
CONTAINER_LOGS_DIR = "/logs"
CONTAINER_REPRO_DIR = "/repro"
DEFAULT_REPLAY_TIMEOUT_SECONDS = 1200
DEFAULT_DOCKER_CONTROL_TIMEOUT_SECONDS = 30
DEFAULT_DOCKER_CLEANUP_TIMEOUT_SECONDS = 20
_REPLAY_CREATE_RECONCILE_COMMAND_TIMEOUT_SECONDS = 2.0
_REPLAY_CREATE_RECONCILE_POLL_SECONDS = 0.5
_IMAGE_ID_RE = re.compile(r"sha256:[0-9a-f]{64}")


def _positive_int_from_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


@dataclass
class RuntimeConfig:
    image: str = "autocompiler:gcc13"
    network: str = DEFAULT_NETWORK
    remove_on_cleanup: bool = True
    replay_timeout_seconds: int = field(
        default_factory=lambda: _positive_int_from_env(
            "COMPILE_REPLAY_TIMEOUT_SECONDS",
            DEFAULT_REPLAY_TIMEOUT_SECONDS,
        )
    )
    docker_control_timeout_seconds: int = field(
        default_factory=lambda: _positive_int_from_env(
            "COMPILE_DOCKER_CONTROL_TIMEOUT_SECONDS",
            DEFAULT_DOCKER_CONTROL_TIMEOUT_SECONDS,
        )
    )
    cleanup_timeout_seconds: int = field(
        default_factory=lambda: _positive_int_from_env(
            "COMPILE_DOCKER_CLEANUP_TIMEOUT_SECONDS",
            DEFAULT_DOCKER_CLEANUP_TIMEOUT_SECONDS,
        )
    )


@dataclass(frozen=True)
class ContainerCleanupResult:
    succeeded: bool
    stopped: bool
    removed: bool


@dataclass(frozen=True)
class ReplayContainerHandle:
    container_id: str
    container_name: str
    image_id: str


class CompileDockerRuntime:
    def __init__(self, config: RuntimeConfig | None = None, manager=None):
        self.config = config or RuntimeConfig(
            network=os.getenv("COMPILE_RUNTIME_NETWORK") or DEFAULT_NETWORK,
        )
        self.manager = manager

    @staticmethod
    def _runtime_proxy_environment() -> tuple[list[str], dict[str, str]]:
        environment = os.environ.copy()
        docker_flags: list[str] = []
        proxy_variables = (
            ("COMPILE_RUNTIME_HTTP_PROXY", "HTTP_PROXY", "http_proxy"),
            ("COMPILE_RUNTIME_HTTPS_PROXY", "HTTPS_PROXY", "https_proxy"),
            ("COMPILE_RUNTIME_NO_PROXY", "NO_PROXY", "no_proxy"),
        )
        for source_name, upper_name, lower_name in proxy_variables:
            value = os.getenv(source_name)
            if not value:
                continue
            environment[upper_name] = value
            environment[lower_name] = value
            docker_flags.extend(["-e", upper_name, "-e", lower_name])
        return docker_flags, environment

    def _paths(self) -> Paths:
        manager_paths = getattr(self.manager, "paths", None)
        return manager_paths or Paths()

    def _host_session_dir(self, session: CompileSession) -> str:
        return get_host_session_dir(session.session_id, session.thread_id, self._paths())

    def _host_workspace_dir(self, session: CompileSession) -> str:
        return get_host_workspace_dir(session.session_id, session.thread_id, self._paths())

    def _host_artifacts_dir(self, session: CompileSession) -> str:
        return get_host_artifacts_dir(session.session_id, session.thread_id, self._paths())

    def _host_logs_dir(self, session: CompileSession) -> str:
        return get_host_logs_dir(session.session_id, session.thread_id, self._paths())

    def _host_repro_dir(self, session: CompileSession) -> str:
        return get_host_repro_dir(session.session_id, session.thread_id, self._paths())

    def _host_replay_recipe_dir(self, session: CompileSession, attempt_id: str) -> str:
        return get_host_replay_recipe_dir(
            session.session_id,
            session.thread_id,
            attempt_id,
            self._paths(),
        )

    def _host_replay_workspace_dir(self, session: CompileSession, attempt_id: str) -> str:
        return get_host_replay_workspace_dir(
            session.session_id,
            session.thread_id,
            attempt_id,
            self._paths(),
        )

    def _host_replay_artifacts_dir(self, session: CompileSession, attempt_id: str) -> str:
        return get_host_replay_artifacts_dir(
            session.session_id,
            session.thread_id,
            attempt_id,
            self._paths(),
        )

    def _host_replay_logs_dir(self, session: CompileSession, attempt_id: str) -> str:
        return get_host_replay_logs_dir(
            session.session_id,
            session.thread_id,
            attempt_id,
            self._paths(),
        )

    def _log(self, session: CompileSession, event: str, **payload) -> None:
        if self.manager is not None:
            self.manager.log_event(session, event, **payload)

    @staticmethod
    def _validate_image_id(image_id: str) -> str:
        normalized = image_id.strip().lower()
        if not _IMAGE_ID_RE.fullmatch(normalized):
            raise RuntimeError(f"Docker returned an invalid immutable image ID: {image_id!r}")
        return normalized

    @staticmethod
    def _remaining_timeout(deadline: float, *, command: list[str], timeout_budget: int) -> int:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, timeout_budget)
        return max(1, math.ceil(remaining))

    @staticmethod
    def _timeout_output(value: str | bytes | None) -> str:
        if isinstance(value, bytes):
            return value.decode(errors="replace")
        return value or ""

    def inspect_container_image_id(
        self,
        container_reference: str,
        *,
        timeout_seconds: int | None = None,
    ) -> str:
        command = ["docker", "inspect", "--format", "{{.Image}}", container_reference]
        effective_timeout = max(1, timeout_seconds or self.config.docker_control_timeout_seconds)
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
        )
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip() or "unknown Docker error"
            raise RuntimeError(f"Failed to inspect immutable image ID for container {container_reference!r}: {error}")
        return self._validate_image_id(result.stdout)

    def _reconcile_timed_out_replay_create(
        self,
        session: CompileSession,
        *,
        container_name: str,
    ) -> None:
        timeout_budget = max(1, self.config.cleanup_timeout_seconds)
        deadline = time.monotonic() + timeout_budget
        del session
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            command = ["docker", "rm", "-f", container_name]
            command_timeout = min(_REPLAY_CREATE_RECONCILE_COMMAND_TIMEOUT_SECONDS, remaining)
            try:
                result = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=command_timeout,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
            else:
                if result.returncode == 0:
                    break

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(_REPLAY_CREATE_RECONCILE_POLL_SECONDS, remaining))

    @staticmethod
    def replay_container_name(session: CompileSession, attempt_id: str) -> str:
        safe_thread_id = re.sub(r"[^A-Za-z0-9_.-]", "-", session.thread_id)[:8]
        safe_session_id = re.sub(r"[^A-Za-z0-9_.-]", "-", session.session_id)[:8]
        safe_attempt_id = re.sub(r"[^A-Za-z0-9_.-]", "-", attempt_id)[:12]
        if not safe_thread_id or not safe_session_id or not safe_attempt_id:
            raise ValueError("A replay attempt ID is required to create a replay container")
        return f"deerflow-replay-{safe_thread_id}-{safe_session_id}-{safe_attempt_id}"

    def _ensure_network(self, *, timeout_seconds: int | None = None) -> None:
        effective_timeout = max(1, timeout_seconds or self.config.docker_control_timeout_seconds)
        deadline = time.monotonic() + effective_timeout
        inspect_command = ["docker", "network", "inspect", self.config.network]
        inspected = subprocess.run(
            inspect_command,
            check=False,
            capture_output=True,
            text=True,
            timeout=self._remaining_timeout(
                deadline,
                command=inspect_command,
                timeout_budget=effective_timeout,
            ),
        )
        if inspected.returncode == 0:
            return

        create_command = ["docker", "network", "create", self.config.network]
        created = subprocess.run(
            create_command,
            check=False,
            capture_output=True,
            text=True,
            timeout=self._remaining_timeout(
                deadline,
                command=create_command,
                timeout_budget=effective_timeout,
            ),
        )
        if created.returncode == 0:
            return

        # Another process may have created the network between inspect and create.
        inspected = subprocess.run(
            inspect_command,
            check=False,
            capture_output=True,
            text=True,
            timeout=self._remaining_timeout(
                deadline,
                command=inspect_command,
                timeout_budget=effective_timeout,
            ),
        )
        if inspected.returncode != 0:
            error = created.stderr.strip() or inspected.stderr.strip() or "unknown Docker error"
            raise RuntimeError(f"Failed to create Docker network {self.config.network!r}: {error}")

    def create_container(self, session: CompileSession) -> str:
        if session.container_id:
            inspected_image_id = self.inspect_container_image_id(session.container_id)
            if session.image_id and self._validate_image_id(session.image_id) != inspected_image_id:
                raise RuntimeError("The existing compile container image does not match the recorded immutable image ID")
            session.image_id = inspected_image_id
            self._log(
                session,
                "container.reused",
                container_id=session.container_id,
                container_name=session.container_name,
                image_id=session.image_id,
            )
            return session.container_id

        self._ensure_network()
        host_workspace_dir = self._host_workspace_dir(session)
        host_artifacts_dir = self._host_artifacts_dir(session)
        host_logs_dir = self._host_logs_dir(session)
        host_repro_dir = self._host_repro_dir(session)
        proxy_flags, run_environment = self._runtime_proxy_environment()
        container_name = f"deerflow-compile-{session.thread_id[:8]}-{session.session_id[:8]}"
        command = [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "--network",
            self.config.network,
            "--add-host",
            "host.docker.internal:host-gateway",
            *proxy_flags,
            "-v",
            f"{host_workspace_dir}:{CONTAINER_WORKSPACE_DIR}",
            "-v",
            f"{host_artifacts_dir}:{CONTAINER_ARTIFACTS_DIR}",
            "-v",
            f"{host_logs_dir}:{CONTAINER_LOGS_DIR}",
            "-v",
            f"{host_repro_dir}:{CONTAINER_REPRO_DIR}",
            "-w",
            CONTAINER_WORKSPACE_DIR,
            session.image or self.config.image,
            "tail",
            "-f",
            "/dev/null",
        ]
        self._log(
            session,
            "container.create.started",
            container_name=container_name,
            image=session.image or self.config.image,
            network=self.config.network,
            mounts={
                str(host_workspace_dir): CONTAINER_WORKSPACE_DIR,
                str(host_artifacts_dir): CONTAINER_ARTIFACTS_DIR,
                str(host_logs_dir): CONTAINER_LOGS_DIR,
                str(host_repro_dir): CONTAINER_REPRO_DIR,
            },
            workdir=CONTAINER_WORKSPACE_DIR,
            docker_command=command,
        )
        started_at = utc_now_iso()
        result = subprocess.run(command, check=True, capture_output=True, text=True, env=run_environment)
        session.container_name = container_name
        session.container_id = result.stdout.strip()
        try:
            session.image_id = self.inspect_container_image_id(session.container_id)
        except BaseException:
            self.stop_and_remove_container_reference(
                session,
                container_id=session.container_id,
                container_name=session.container_name,
                role="compile",
                force_remove=True,
            )
            session.container_id = None
            session.container_name = None
            raise
        self._log(
            session,
            "container.create.completed",
            container_id=session.container_id,
            container_name=container_name,
            image_id=session.image_id,
            started_at=started_at,
            completed_at=utc_now_iso(),
            stdout=result.stdout,
            stderr=result.stderr,
        )
        return session.container_id

    def create_replay_container(
        self,
        session: CompileSession,
        *,
        attempt_id: str,
        timeout_seconds: int | None = None,
    ) -> ReplayContainerHandle:
        effective_timeout = max(1, timeout_seconds or self.config.replay_timeout_seconds)
        deadline = time.monotonic() + effective_timeout
        image_id = self._validate_image_id(session.image_id or "")
        paths = self._paths()
        recipe_dir = get_replay_recipe_dir(
            session.session_id,
            session.thread_id,
            attempt_id,
            paths,
        )
        workspace_dir = get_replay_workspace_dir(
            session.session_id,
            session.thread_id,
            attempt_id,
            paths,
        )
        artifacts_dir = get_replay_artifacts_dir(
            session.session_id,
            session.thread_id,
            attempt_id,
            paths,
        )
        logs_dir = get_replay_logs_dir(
            session.session_id,
            session.thread_id,
            attempt_id,
            paths,
        )
        for directory in (recipe_dir, workspace_dir, artifacts_dir, logs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        recipe_path = recipe_dir / "build.sh"
        if recipe_path.is_symlink() or not recipe_path.is_file():
            raise ValueError("Replay recipe/build.sh must be a regular file before container creation")
        for directory in (workspace_dir, artifacts_dir, logs_dir):
            if any(directory.iterdir()):
                raise ValueError(f"Replay {directory.name} directory must be empty before container creation")

        self._ensure_network(
            timeout_seconds=self._remaining_timeout(
                deadline,
                command=["docker", "network", "inspect", self.config.network],
                timeout_budget=effective_timeout,
            )
        )
        host_recipe_dir = self._host_replay_recipe_dir(session, attempt_id)
        host_workspace_dir = self._host_replay_workspace_dir(session, attempt_id)
        host_artifacts_dir = self._host_replay_artifacts_dir(session, attempt_id)
        host_logs_dir = self._host_replay_logs_dir(session, attempt_id)
        proxy_flags, run_environment = self._runtime_proxy_environment()
        container_name = self.replay_container_name(session, attempt_id)
        command = [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "--label",
            "deerflow.compile.role=replay",
            "--label",
            f"deerflow.compile.session_id={session.session_id}",
            "--label",
            f"deerflow.compile.thread_id={session.thread_id}",
            "--label",
            f"deerflow.compile.attempt_id={attempt_id}",
            "--network",
            self.config.network,
            "--add-host",
            "host.docker.internal:host-gateway",
            *proxy_flags,
            "-v",
            f"{host_recipe_dir}:{CONTAINER_REPRO_DIR}:ro",
            "-v",
            f"{host_workspace_dir}:{CONTAINER_WORKSPACE_DIR}",
            "-v",
            f"{host_artifacts_dir}:{CONTAINER_ARTIFACTS_DIR}",
            "-v",
            f"{host_logs_dir}:{CONTAINER_LOGS_DIR}",
            "-w",
            CONTAINER_WORKSPACE_DIR,
            image_id,
            "tail",
            "-f",
            "/dev/null",
        ]
        self._log(
            session,
            "replay.container.create.started",
            attempt_id=attempt_id,
            container_name=container_name,
            image=session.image,
            image_id=image_id,
            network=self.config.network,
            timeout_seconds=effective_timeout,
            mounts={
                host_recipe_dir: f"{CONTAINER_REPRO_DIR}:ro",
                host_workspace_dir: CONTAINER_WORKSPACE_DIR,
                host_artifacts_dir: CONTAINER_ARTIFACTS_DIR,
                host_logs_dir: CONTAINER_LOGS_DIR,
            },
            docker_command=command,
        )
        started_at = utc_now_iso()
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                env=run_environment,
                timeout=self._remaining_timeout(
                    deadline,
                    command=command,
                    timeout_budget=effective_timeout,
                ),
            )
        except subprocess.TimeoutExpired:
            try:
                self._reconcile_timed_out_replay_create(
                    session,
                    container_name=container_name,
                )
            except Exception:
                pass
            raise
        container_id = result.stdout.strip()
        if not container_id:
            self.stop_and_remove_replay_container(
                session,
                container_name=container_name,
            )
            raise RuntimeError("Docker did not return a replay container ID")

        try:
            actual_image_id = self.inspect_container_image_id(
                container_id,
                timeout_seconds=self._remaining_timeout(
                    deadline,
                    command=["docker", "inspect", "--format", "{{.Image}}", container_id],
                    timeout_budget=effective_timeout,
                ),
            )
            if actual_image_id != image_id:
                raise RuntimeError("Replay container image does not match the recorded immutable image ID")
        except BaseException:
            self.stop_and_remove_replay_container(
                session,
                container_id=container_id,
                container_name=container_name,
            )
            raise

        handle = ReplayContainerHandle(
            container_id=container_id,
            container_name=container_name,
            image_id=actual_image_id,
        )
        self._log(
            session,
            "replay.container.create.completed",
            attempt_id=attempt_id,
            container_id=container_id,
            container_name=container_name,
            image=session.image,
            image_id=actual_image_id,
            started_at=started_at,
            completed_at=utc_now_iso(),
            stdout=result.stdout,
            stderr=result.stderr,
        )
        return handle

    def exec_container(
        self,
        session: CompileSession,
        *,
        container_id: str,
        command: str,
        workdir: str | None = None,
        timeout_seconds: int = 600,
        log_path: str | None = None,
        event_prefix: str = "container.exec",
    ) -> CommandResult:
        if not container_id:
            raise ValueError("A container ID is required to execute a compile command")
        container_workdir = workdir or CONTAINER_REPO_DIR
        container_timeout = max(1, timeout_seconds)
        exec_command = [
            "docker",
            "exec",
            "-w",
            container_workdir,
            container_id,
            "timeout",
            "--signal=TERM",
            "--kill-after=5s",
            f"{container_timeout}s",
            "bash",
            "-lc",
            command,
        ]
        self._log(
            session,
            f"{event_prefix}.started",
            container_id=container_id,
            workdir=container_workdir,
            timeout_seconds=container_timeout,
            log_path=log_path,
            command=command,
            docker_command=exec_command,
        )
        started_at = utc_now_iso()
        try:
            result = subprocess.run(exec_command, capture_output=True, text=True, timeout=container_timeout + 10)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            timeout_message = f"Docker exec did not return after the {container_timeout}-second container timeout."
            combined_output = stdout + stderr
            if combined_output and not combined_output.endswith("\n"):
                combined_output += "\n"
            combined_output += timeout_message + "\n"
            if log_path:
                log_file = Path(log_path)
                log_file.parent.mkdir(parents=True, exist_ok=True)
                log_file.write_text(combined_output, encoding="utf-8")
            self._log(
                session,
                f"{event_prefix}.timed_out",
                container_id=container_id,
                workdir=container_workdir,
                timeout_seconds=container_timeout,
                log_path=log_path,
                command=command,
                started_at=started_at,
                completed_at=utc_now_iso(),
                exit_code=124,
                stdout=stdout,
                stderr=stderr,
            )
            return CommandResult(
                exit_code=124,
                stdout=stdout,
                stderr=stderr,
                combined_output=combined_output,
                log_path=log_path,
            )
        combined_output = (result.stdout or "") + (result.stderr or "")
        if log_path:
            log_file = Path(log_path)
            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_file.write_text(combined_output, encoding="utf-8")
        self._log(
            session,
            f"{event_prefix}.completed",
            container_id=container_id,
            workdir=container_workdir,
            timeout_seconds=container_timeout,
            log_path=log_path,
            command=command,
            started_at=started_at,
            completed_at=utc_now_iso(),
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
        return CommandResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            combined_output=combined_output,
            log_path=log_path,
        )

    def exec(
        self,
        session: CompileSession,
        command: str,
        workdir: str | None = None,
        timeout_seconds: int = 600,
        log_path: str | None = None,
    ) -> CommandResult:
        if not session.container_id:
            raise ValueError("Compile session container has not been created")
        return self.exec_container(
            session,
            container_id=session.container_id,
            command=command,
            workdir=workdir,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
        )

    def exec_replay_container(
        self,
        session: CompileSession,
        handle: ReplayContainerHandle,
        command: str = "bash /repro/build.sh",
        workdir: str = CONTAINER_WORKSPACE_DIR,
        timeout_seconds: int | None = None,
        log_path: str | None = None,
    ) -> CommandResult:
        recorded_image_id = self._validate_image_id(session.image_id or "")
        if recorded_image_id != handle.image_id:
            raise ValueError("Replay container image does not match the compile session image identity")
        return self.exec_container(
            session,
            container_id=handle.container_id,
            command=command,
            workdir=workdir,
            timeout_seconds=timeout_seconds or self.config.replay_timeout_seconds,
            log_path=log_path,
            event_prefix="replay.container.exec",
        )

    def copy_artifact_to_session(self, session: CompileSession, source_path: str, destination_filename: str | None = None) -> str:
        if not session.container_id:
            raise ValueError("Compile session container has not been created")

        source = Path(source_path)
        target_name = destination_filename or source.name
        destination_path = f"{CONTAINER_ARTIFACTS_DIR.rstrip('/')}/{target_name}"
        command = f"cp {source_path!r} {destination_path!r}"
        self._log(
            session,
            "artifact.copy.started",
            source_path=source_path,
            destination_path=destination_path,
            command=command,
        )
        result = self.exec(session, command, workdir=CONTAINER_WORKSPACE_DIR)
        if result.exit_code != 0:
            self._log(
                session,
                "artifact.copy.failed",
                source_path=source_path,
                destination_path=destination_path,
                exit_code=result.exit_code,
                output=result.combined_output[:4000],
            )
            raise RuntimeError(f"Failed to copy artifact {source_path} into session artifacts: {result.combined_output}")
        self._log(
            session,
            "artifact.copy.completed",
            source_path=source_path,
            destination_path=destination_path,
            exit_code=result.exit_code,
        )
        return destination_path

    def stop_and_remove_container_reference(
        self,
        session: CompileSession,
        *,
        container_id: str | None = None,
        container_name: str | None = None,
        role: str = "compile",
        force_remove: bool = False,
        timeout_seconds: int | None = None,
    ) -> ContainerCleanupResult:
        container_reference = container_id or container_name
        if not container_reference:
            return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)
        event_prefix = "container.cleanup" if role == "compile" else f"{role}.container.cleanup"
        should_remove = force_remove or self.config.remove_on_cleanup
        effective_timeout = max(2, timeout_seconds or self.config.cleanup_timeout_seconds)
        deadline = time.monotonic() + effective_timeout
        self._log(
            session,
            f"{event_prefix}.started",
            container_id=container_id,
            container_name=container_name,
            container_reference=container_reference,
            force_remove=force_remove,
            remove_on_cleanup=should_remove,
        )
        stop_command = ["docker", "stop", container_reference]
        stop_timeout = min(
            self._remaining_timeout(
                deadline,
                command=stop_command,
                timeout_budget=effective_timeout,
            ),
            max(1, effective_timeout // 2),
        )
        try:
            stop_result = subprocess.run(
                stop_command,
                check=False,
                capture_output=True,
                text=True,
                timeout=stop_timeout,
            )
            stop_returncode = stop_result.returncode
            stop_stdout = stop_result.stdout
            stop_stderr = stop_result.stderr
        except subprocess.TimeoutExpired as exc:
            stop_returncode = 124
            stop_stdout = self._timeout_output(exc.stdout)
            stop_stderr = self._timeout_output(exc.stderr)
        self._log(
            session,
            f"{event_prefix}.stopped",
            container_id=container_id,
            container_name=container_name,
            container_reference=container_reference,
            exit_code=stop_returncode,
            stdout=stop_stdout,
            stderr=stop_stderr,
            timeout_seconds=stop_timeout,
        )
        stop_succeeded = stop_returncode == 0 or "No such container" in stop_stderr
        if should_remove:
            rm_command = ["docker", "rm", "-f", container_reference]
            try:
                rm_timeout = self._remaining_timeout(
                    deadline,
                    command=rm_command,
                    timeout_budget=effective_timeout,
                )
                rm_result = subprocess.run(
                    rm_command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=rm_timeout,
                )
                rm_returncode = rm_result.returncode
                rm_stdout = rm_result.stdout
                rm_stderr = rm_result.stderr
            except subprocess.TimeoutExpired as exc:
                rm_timeout = getattr(exc, "timeout", effective_timeout)
                rm_returncode = 124
                rm_stdout = self._timeout_output(exc.stdout)
                rm_stderr = self._timeout_output(exc.stderr)
            self._log(
                session,
                f"{event_prefix}.removed",
                container_id=container_id,
                container_name=container_name,
                container_reference=container_reference,
                exit_code=rm_returncode,
                stdout=rm_stdout,
                stderr=rm_stderr,
                timeout_seconds=rm_timeout,
            )
            remove_succeeded = rm_returncode == 0 or "No such container" in rm_stderr
            return ContainerCleanupResult(
                succeeded=remove_succeeded,
                stopped=stop_succeeded,
                removed=remove_succeeded,
            )
        return ContainerCleanupResult(
            succeeded=stop_succeeded,
            stopped=stop_succeeded,
            removed=False,
        )

    def stop_and_remove_replay_container(
        self,
        session: CompileSession,
        handle: ReplayContainerHandle | None = None,
        *,
        container_id: str | None = None,
        container_name: str | None = None,
        timeout_seconds: int | None = None,
    ) -> ContainerCleanupResult:
        if handle is not None:
            if container_id and container_id != handle.container_id:
                raise ValueError("Replay cleanup received conflicting container IDs")
            if container_name and container_name != handle.container_name:
                raise ValueError("Replay cleanup received conflicting container names")
            container_id = handle.container_id
            container_name = handle.container_name
        return self.stop_and_remove_container_reference(
            session,
            container_id=container_id,
            container_name=container_name,
            role="replay",
            force_remove=True,
            timeout_seconds=timeout_seconds,
        )

    def stop_and_remove_container(
        self,
        session: CompileSession,
        *,
        timeout_seconds: int | None = None,
    ) -> ContainerCleanupResult:
        return self.stop_and_remove_container_reference(
            session,
            container_id=session.container_id,
            container_name=session.container_name,
            role="compile",
            timeout_seconds=timeout_seconds,
        )

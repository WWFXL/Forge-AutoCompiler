from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from deerflow.compile.paths import get_host_artifacts_dir, get_host_logs_dir, get_host_repro_dir, get_host_session_dir, get_host_workspace_dir
from deerflow.compile.schemas import CommandResult, CompileSession, utc_now_iso
from deerflow.config.paths import Paths

DEFAULT_NETWORK = "compile_network_wwf_v1"
CONTAINER_WORKSPACE_DIR = "/workspace"
CONTAINER_REPO_DIR = "/workspace/repo"
CONTAINER_ARTIFACTS_DIR = "/artifacts"
CONTAINER_LOGS_DIR = "/logs"
CONTAINER_REPRO_DIR = "/repro"


@dataclass
class RuntimeConfig:
    image: str = "autocompiler:gcc13"
    network: str = DEFAULT_NETWORK
    remove_on_cleanup: bool = True


@dataclass(frozen=True)
class ContainerCleanupResult:
    succeeded: bool
    stopped: bool
    removed: bool


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

    def _log(self, session: CompileSession, event: str, **payload) -> None:
        if self.manager is not None:
            self.manager.log_event(session, event, **payload)

    def _ensure_network(self) -> None:
        inspect_command = ["docker", "network", "inspect", self.config.network]
        inspected = subprocess.run(inspect_command, check=False, capture_output=True, text=True)
        if inspected.returncode == 0:
            return

        create_command = ["docker", "network", "create", self.config.network]
        created = subprocess.run(create_command, check=False, capture_output=True, text=True)
        if created.returncode == 0:
            return

        # Another process may have created the network between inspect and create.
        inspected = subprocess.run(inspect_command, check=False, capture_output=True, text=True)
        if inspected.returncode != 0:
            error = created.stderr.strip() or inspected.stderr.strip() or "unknown Docker error"
            raise RuntimeError(f"Failed to create Docker network {self.config.network!r}: {error}")

    def create_container(self, session: CompileSession) -> str:
        if session.container_id:
            self._log(
                session,
                "container.reused",
                container_id=session.container_id,
                container_name=session.container_name,
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
        self._log(
            session,
            "container.create.completed",
            container_id=session.container_id,
            container_name=container_name,
            started_at=started_at,
            completed_at=utc_now_iso(),
            stdout=result.stdout,
            stderr=result.stderr,
        )
        return session.container_id

    def exec(self, session: CompileSession, command: str, workdir: str | None = None, timeout_seconds: int = 600, log_path: str | None = None) -> CommandResult:
        if not session.container_id:
            raise ValueError("Compile session container has not been created")

        container_workdir = workdir or CONTAINER_REPO_DIR
        container_timeout = max(1, timeout_seconds)
        exec_command = [
            "docker",
            "exec",
            "-w",
            container_workdir,
            session.container_id,
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
            "container.exec.started",
            container_id=session.container_id,
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
                Path(log_path).write_text(combined_output, encoding="utf-8")
            self._log(
                session,
                "container.exec.timed_out",
                container_id=session.container_id,
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
            Path(log_path).write_text(combined_output, encoding="utf-8")
        self._log(
            session,
            "container.exec.completed",
            container_id=session.container_id,
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

    def stop_and_remove_container(self, session: CompileSession) -> ContainerCleanupResult:
        if not session.container_id:
            return ContainerCleanupResult(succeeded=True, stopped=True, removed=True)
        self._log(
            session,
            "container.cleanup.started",
            container_id=session.container_id,
            remove_on_cleanup=self.config.remove_on_cleanup,
        )
        stop_result = subprocess.run(["docker", "stop", session.container_id], check=False, capture_output=True, text=True)
        self._log(
            session,
            "container.cleanup.stopped",
            container_id=session.container_id,
            exit_code=stop_result.returncode,
            stdout=stop_result.stdout,
            stderr=stop_result.stderr,
        )
        stop_succeeded = stop_result.returncode == 0 or "No such container" in (stop_result.stderr or "")
        if self.config.remove_on_cleanup:
            rm_result = subprocess.run(["docker", "rm", "-f", session.container_id], check=False, capture_output=True, text=True)
            self._log(
                session,
                "container.cleanup.removed",
                container_id=session.container_id,
                exit_code=rm_result.returncode,
                stdout=rm_result.stdout,
                stderr=rm_result.stderr,
            )
            remove_succeeded = rm_result.returncode == 0 or "No such container" in (rm_result.stderr or "")
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

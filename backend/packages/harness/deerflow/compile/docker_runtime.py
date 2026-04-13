from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from deerflow.compile.schemas import CommandResult, CompileSession

DEFAULT_NETWORK = "compile_network_wwf_v1"


@dataclass
class RuntimeConfig:
    image: str = "autocompiler:gcc13"
    network: str = DEFAULT_NETWORK
    remove_on_cleanup: bool = True


class CompileDockerRuntime:
    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig()

    def create_container(self, session: CompileSession) -> str:
        if session.container_id:
            return session.container_id

        container_name = f"deerflow-compile-{session.thread_id[:8]}-{session.session_id[:8]}"
        command = [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "--network",
            self.config.network,
            "-v",
            f"{session.host_workspace_dir}:{session.container_workspace_dir}",
            "-v",
            f"{session.host_artifacts_dir}:{session.container_artifacts_dir}",
            "-v",
            f"{session.host_logs_dir}:{session.container_logs_dir}",
            "-v",
            f"{session.host_repro_dir}:{session.container_repro_dir}",
            "-w",
            session.container_workspace_dir,
            session.image or self.config.image,
            "sleep",
            "infinity",
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        session.container_name = container_name
        session.container_id = result.stdout.strip()
        return session.container_id

    def exec(self, session: CompileSession, command: str, workdir: str | None = None, timeout_seconds: int = 600, log_path: str | None = None) -> CommandResult:
        if not session.container_id:
            raise ValueError("Compile session container has not been created")

        container_workdir = workdir or session.container_repo_dir
        exec_command = [
            "docker",
            "exec",
            "-w",
            container_workdir,
            session.container_id,
            "bash",
            "-lc",
            command,
        ]
        result = subprocess.run(exec_command, capture_output=True, text=True, timeout=timeout_seconds)
        combined_output = (result.stdout or "") + (result.stderr or "")
        if log_path:
            Path(log_path).write_text(combined_output, encoding="utf-8")
        return CommandResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            combined_output=combined_output,
            log_path=log_path,
        )

    def stop_and_remove_container(self, session: CompileSession) -> None:
        if not session.container_id:
            return
        subprocess.run(["docker", "stop", session.container_id], check=False, capture_output=True, text=True)
        if self.config.remove_on_cleanup:
            subprocess.run(["docker", "rm", "-f", session.container_id], check=False, capture_output=True, text=True)


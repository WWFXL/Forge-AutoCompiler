from __future__ import annotations

from langchain.tools import tool

from deerflow.compile.operations import run_compile_command_impl
from deerflow.compile.schemas import CompileSession


def get_bound_compile_tools(session: CompileSession):
    @tool("run_compile_command", parse_docstring=True)
    def bound_run_compile_command(
        command: str,
        workdir: str | None = None,
        timeout_seconds: int = 1200,
        stage: str | None = None,
    ) -> str:
        """Run a build command inside the bound compile session container.

        Args:
            command: Shell command to run.
            workdir: Optional subdirectory under `/workspace/repo`.
            timeout_seconds: Command timeout in seconds.
            stage: Optional logical stage label (e.g. configure/build/test).
        """
        _, _, message = run_compile_command_impl(
            session=session,
            command=command,
            workdir=workdir,
            timeout_seconds=timeout_seconds,
            stage=stage,
        )
        return message

    return [bound_run_compile_command]


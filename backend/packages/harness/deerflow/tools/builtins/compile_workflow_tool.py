from __future__ import annotations

from typing import Annotated

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.compile.workflow import CompileWorkflowInput, CompileWorkflowRunner
from deerflow.tools.builtins.compile_tools import _get_subagent_owner_id, _get_thread_id


@tool("run_compile_workflow", parse_docstring=True)
def run_compile_workflow(
    runtime: ToolRuntime[ContextT, ThreadState],
    repo_url: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    branch: str | None = None,
    task_description: str | None = None,
    artifact_hint: str | None = None,
    build_goal: str | None = None,
    max_build_attempts: int = 4,
    generate_repro_bundle: bool = True,
) -> str:
    """Run the compile workflow for a remote repository.

    Args:
        repo_url: Git repository URL to compile.
        branch: Optional branch to checkout.
        task_description: Optional short summary of the compile task.
        artifact_hint: Optional expected artifact name or file pattern.
        build_goal: Optional explicit build goal such as release binary.
        max_build_attempts: Maximum build attempts allowed inside the workflow.
        generate_repro_bundle: Whether to generate repro files during finalize.
    """
    del tool_call_id

    runner = CompileWorkflowRunner()
    result = runner.run(
        CompileWorkflowInput(
            repo_url=repo_url,
            thread_id=_get_thread_id(runtime),
            branch=branch,
            task_description=task_description,
            artifact_hint=artifact_hint,
            build_goal=build_goal,
            max_build_attempts=max_build_attempts,
            owner_id=_get_subagent_owner_id(runtime),
            generate_repro_bundle=generate_repro_bundle,
        )
    )

    attempts_summary = "\n".join(
        f"- [{attempt.stage}] exit={attempt.exit_code} cmd={attempt.command}" for attempt in result.attempts
    ) or "- none"
    artifact_summary = "\n".join(f"- {path}" for path in result.artifacts) or "- none"
    log_summary = "\n".join(f"- {path}" for path in result.logs) or "- none"
    repro_summary = "\n".join(f"- {path}" for path in result.repro_files) or "- none"

    lines = [
        f"Compile workflow {result.status}.",
        f"Summary: {result.summary}",
        f"Session: {result.session_id or 'unknown'}",
        f"Build system: {result.build_system or 'unknown'}",
        f"Attempts:\n{attempts_summary}",
        f"Artifacts:\n{artifact_summary}",
        f"Logs:\n{log_summary}",
        f"Repro files:\n{repro_summary}",
    ]
    if result.verify_message:
        lines.append(f"Verify: {result.verify_message}")
    lines.append(f"Error: {result.error or 'none'}")
    return "\n".join(lines)

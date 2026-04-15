from __future__ import annotations

import json
from dataclasses import dataclass

from deerflow.compile.schemas import CompileSession
from deerflow.compile.workflow.schemas import BuildSubagentResult, CompileWorkflowInput
from deerflow.subagents import SubagentExecutor, get_subagent_config
from deerflow.subagents.executor import SubagentStatus
from deerflow.tools.tools import get_subagent_tools


@dataclass
class BuildSubagentExecutionResult:
    subagent_status: SubagentStatus
    parsed_result: BuildSubagentResult | None
    raw_output: str
    error: str | None = None


_BUILD_RESULT_JSON_SCHEMA = {
    "type": "object",
    "required": ["build_status", "proceed_to_verify", "summary"],
}


def _build_prompt(workflow_input: CompileWorkflowInput, build_system: str | None) -> str:
    payload = {
        "repo_url": workflow_input.repo_url,
        "branch": workflow_input.branch,
        "build_system": build_system,
        "task_description": workflow_input.task_description,
        "artifact_hint": workflow_input.artifact_hint,
        "build_goal": workflow_input.build_goal,
        "max_build_attempts": workflow_input.max_build_attempts,
    }
    return (
        "Complete the build stage for the already prepared compile session. "
        "Use run_compile_command for all actions. Return only the required JSON contract at the end.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _parse_build_result(raw_output: str) -> BuildSubagentResult:
    data = json.loads(raw_output)
    build_status = str(data.get("build_status", "")).strip()
    proceed_to_verify = bool(data.get("proceed_to_verify", False))
    summary = str(data.get("summary", "")).strip()

    if build_status not in {"success", "failed"}:
        raise ValueError(f"Invalid build_status: {build_status!r}")
    if not summary:
        raise ValueError("Missing summary in build subagent result")
    if build_status == "failed" and proceed_to_verify:
        raise ValueError("Failed build cannot proceed to verify")
    if build_status == "success" and not proceed_to_verify:
        raise ValueError("Successful build must proceed to verify")

    return BuildSubagentResult(
        build_status=build_status,
        proceed_to_verify=proceed_to_verify,
        summary=summary,
        raw_output=raw_output,
    )


def run_build_subagent_once(
    *,
    session: CompileSession,
    workflow_input: CompileWorkflowInput,
    build_system: str | None,
) -> BuildSubagentExecutionResult:
    del session

    config = get_subagent_config("compiler")
    if config is None:
        raise RuntimeError("Compiler subagent config not found")

    tools = get_subagent_tools(subagent_type="compiler", model_name=None)
    executor = SubagentExecutor(
        config=config,
        tools=tools,
        thread_id=workflow_input.thread_id,
        trace_id=workflow_input.owner_id or "build-workflow",
    )

    result = executor.execute(_build_prompt(workflow_input, build_system))
    raw_output = result.result or ""

    if result.status != SubagentStatus.COMPLETED:
        return BuildSubagentExecutionResult(
            subagent_status=result.status,
            parsed_result=None,
            raw_output=raw_output,
            error=result.error or f"Build subagent ended with status {result.status.value}",
        )

    try:
        parsed = _parse_build_result(raw_output)
    except Exception as exc:
        return BuildSubagentExecutionResult(
            subagent_status=result.status,
            parsed_result=None,
            raw_output=raw_output,
            error=str(exc),
        )

    return BuildSubagentExecutionResult(
        subagent_status=result.status,
        parsed_result=parsed,
        raw_output=raw_output,
        error=None,
    )


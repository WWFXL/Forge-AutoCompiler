from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from deerflow.compile.schemas import CompileSession
from deerflow.compile.workflow.schemas import BuildSubagentResult, CompileWorkflowInput
from deerflow.subagents import SubagentExecutor, get_subagent_config
from deerflow.subagents.executor import SubagentStatus
from deerflow.tools.bound_compile_tools import get_bound_compile_tools

logger = logging.getLogger(__name__)


@dataclass
class BuildSubagentExecutionResult:
    subagent_status: SubagentStatus
    parsed_result: BuildSubagentResult | None
    raw_output: str
    error: str | None = None


_BUILD_RESULT_JSON_SCHEMA = {
    "type": "object",
    "required": ["build_status", "proceed_to_verify", "summary", "artifacts"],
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
        "Use run_compile_command for all actions. "
        "Return only the required JSON contract at the end. "
        "The JSON must include 'artifacts', an array of absolute artifact paths inside the compile container, for example ['/workspace/repo/ffmpeg']."
        "\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _parse_build_result(raw_output: str) -> BuildSubagentResult:
    data = json.loads(raw_output)
    build_status = str(data.get("build_status", "")).strip()
    proceed_to_verify = bool(data.get("proceed_to_verify", False))
    summary = str(data.get("summary", "")).strip()
    artifacts_raw = data.get("artifacts", [])

    if build_status not in {"success", "failed"}:
        raise ValueError(f"Invalid build_status: {build_status!r}")
    if not summary:
        raise ValueError("Missing summary in build subagent result")
    if not isinstance(artifacts_raw, list) or any(not isinstance(item, str) for item in artifacts_raw):
        raise ValueError("artifacts must be an array of strings")
    if build_status == "failed" and proceed_to_verify:
        raise ValueError("Failed build cannot proceed to verify")
    if build_status == "success" and not proceed_to_verify:
        raise ValueError("Successful build must proceed to verify")

    artifacts = [item.strip() for item in artifacts_raw if item.strip()]
    if build_status == "success" and not artifacts:
        raise ValueError("Successful build must provide at least one artifact path")

    return BuildSubagentResult(
        build_status=build_status,
        proceed_to_verify=proceed_to_verify,
        summary=summary,
        artifacts=artifacts,
        raw_output=raw_output,
    )


def run_build_subagent_once(
    *,
    session: CompileSession,
    workflow_input: CompileWorkflowInput,
    build_system: str | None,
) -> BuildSubagentExecutionResult:
    logger.info(
        "Running build subagent once: session_id=%s thread_id=%s build_system=%s",
        session.session_id,
        workflow_input.thread_id,
        build_system,
    )

    config = get_subagent_config("compiler")
    if config is None:
        raise RuntimeError("Compiler subagent config not found")

    tools = get_bound_compile_tools(session)
    executor = SubagentExecutor(
        config=config,
        tools=tools,
        thread_id=workflow_input.thread_id,
        trace_id=workflow_input.owner_id or session.session_id,
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

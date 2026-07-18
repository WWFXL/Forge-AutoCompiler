"""Task tool for delegating work to subagents."""

import asyncio
import inspect
import json
import logging
import uuid
from dataclasses import replace
from typing import Annotated

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langgraph.config import get_stream_writer
from langgraph.typing import ContextT

from deerflow.agents.lead_agent.prompt import get_skills_prompt_section
from deerflow.agents.thread_state import ThreadState
from deerflow.compile.evidence import ExperimentPolicy
from deerflow.subagents import SubagentExecutor, get_available_subagent_names, get_subagent_config
from deerflow.subagents.executor import (
    SubagentStatus,
    cleanup_background_task,
    get_background_task_result,
    request_cancel_background_task,
    wait_for_background_task_shutdown,
)
from deerflow.tools.builtins.agent_compile_tools import (
    COMPILE_BUILD_SYSTEM_STATE_KEY,
    COMPILE_CONTAINER_STATE_KEY,
    COMPILE_SESSION_STATE_KEY,
)

logger = logging.getLogger(__name__)


def _apply_max_turns_override(config, *, subagent_type: str, requested_max_turns: int | None):
    if requested_max_turns is None or subagent_type == "compiler":
        return config
    return replace(config, max_turns=requested_max_turns)


def _with_benchmark_constraints(prompt: str, policy: ExperimentPolicy) -> str:
    requirements = [
        "Active C/C++ benchmark constraints:",
        f"- Build exact commit {policy.expected_commit_sha} from {policy.expected_repo_url}.",
        "- The runner already applies the declared system packages, container environment, and replay delay.",
    ]
    if policy.cmake_arguments:
        requirements.append(f"- Every relevant CMake configure command must include these exact argument tokens in this order: {json.dumps(list(policy.cmake_arguments), ensure_ascii=True)}.")
    if policy.configure_arguments:
        requirements.append(f"- Every relevant Autotools configure command must include these exact argument tokens in this order: {json.dumps(list(policy.configure_arguments), ensure_ascii=True)}.")
    requirements.extend(
        [
            "- Set command_role on every run_container_bash call; use configure for configuration and build for the successful command that supports final acceptance.",
            "- Pass that successful build command's returned command_id as supporting_command_id to submit_build_result.",
        ]
    )
    return f"{prompt.rstrip()}\n\n" + "\n".join(requirements)


def _get_compile_state(runtime: ToolRuntime[ContextT, ThreadState]) -> dict[str, str]:
    state = runtime.state or {}
    context = runtime.context or {}
    compile_state: dict[str, str] = {}
    for key in (
        COMPILE_SESSION_STATE_KEY,
        COMPILE_CONTAINER_STATE_KEY,
        COMPILE_BUILD_SYSTEM_STATE_KEY,
    ):
        value = state.get(key) or context.get(key)
        if value:
            compile_state[key] = value
    return compile_state


async def _cancel_and_reap_task(
    *,
    task_id: str,
    subagent_type: str,
    compile_state: dict[str, str],
    thread_id: str | None,
    terminal_status: str,
    error: str,
    shutdown_timeout_seconds: float,
) -> bool:
    request_cancel_background_task(task_id)
    cleanup_result = None

    if subagent_type == "compiler" and thread_id:
        session_id = compile_state.get(COMPILE_SESSION_STATE_KEY)
        if session_id:
            from deerflow.agents.middlewares.tool_error_handling_middleware import load_bound_session_async
            from deerflow.compile.operations import cleanup_compile_session_container_impl

            try:
                session = await load_bound_session_async(session_id=session_id, thread_id=thread_id)
                _updated, cleanup_result = await asyncio.to_thread(
                    cleanup_compile_session_container_impl,
                    session=session,
                    interrupted_status=terminal_status,
                    error=error,
                )
            except Exception:
                logger.exception("Failed to stop compile container while terminating task %s", task_id)

    shutdown_result = wait_for_background_task_shutdown(task_id, shutdown_timeout_seconds)
    worker_stopped = await shutdown_result if inspect.isawaitable(shutdown_result) else bool(shutdown_result)
    if not worker_stopped:
        logger.error("Task %s did not stop within %.1fs after cancellation", task_id, shutdown_timeout_seconds)
        return False

    if subagent_type == "compiler" and thread_id:
        session_id = compile_state.get(COMPILE_SESSION_STATE_KEY)
        if session_id:
            from deerflow.agents.middlewares.tool_error_handling_middleware import load_bound_session_async
            from deerflow.compile.operations import cleanup_compile_session_container_impl, finalize_compile_session_impl, get_compile_services

            try:
                session = await load_bound_session_async(session_id=session_id, thread_id=thread_id)
                session, cleanup_result = await asyncio.to_thread(
                    cleanup_compile_session_container_impl,
                    session=session,
                    interrupted_status=terminal_status,
                    error=error,
                )
                cleanup_succeeded = cleanup_result is not None and cleanup_result.succeeded
                if cleanup_succeeded:
                    await asyncio.to_thread(
                        finalize_compile_session_impl,
                        session=session,
                        status=terminal_status,
                        summary=error,
                        error=error,
                    )
                else:
                    services = get_compile_services()
                    cleanup_error = f"{error} Compile container cleanup failed."
                    await asyncio.to_thread(
                        services.manager.mark_session_status,
                        session,
                        "failed",
                        error=cleanup_error,
                        summary=cleanup_error,
                    )
            except Exception:
                logger.exception("Failed to finalize compile session while terminating task %s", task_id)

    cleanup_background_task(task_id)
    return True


@tool("task", parse_docstring=True)
async def task_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    description: str,
    prompt: str,
    subagent_type: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    max_turns: int | None = None,
) -> str:
    """Delegate a task to a specialized subagent that runs in its own context.

    Subagents help you:
    - Preserve context by keeping exploration and implementation separate
    - Handle complex multi-step tasks autonomously
    - Execute commands or operations in isolated contexts

    Available subagent types depend on the active sandbox configuration:
    - **general-purpose**: A capable agent for complex, multi-step tasks that require
      both exploration and action. Use when the task requires complex reasoning,
      multiple dependent steps, or would benefit from isolated context.
    - **bash**: Command execution specialist for running bash commands. This is only
      available when host bash is explicitly allowed or when using an isolated shell
      sandbox such as `AioSandboxProvider`.
    - **compiler**: Isolated remote-repository compilation specialist using a dedicated compile container workflow.

    When to use this tool:
    - Complex tasks requiring multiple steps or tools
    - Tasks that produce verbose output
    - When you want to isolate context from the main conversation
    - Parallel research or exploration tasks

    When NOT to use this tool:
    - Simple, single-step operations (use tools directly)
    - Tasks requiring user interaction or clarification

    Args:
        description: A short (3-5 word) description of the task for logging/display. ALWAYS PROVIDE THIS PARAMETER FIRST.
        prompt: The task description for the subagent. Be specific and clear about what needs to be done. ALWAYS PROVIDE THIS PARAMETER SECOND.
        subagent_type: The type of subagent to use. ALWAYS PROVIDE THIS PARAMETER THIRD.
        max_turns: Optional maximum number of agent turns. Defaults to subagent's configured max.
    """
    available_subagent_names = get_available_subagent_names()

    config = get_subagent_config(subagent_type)
    if config is None:
        available = ", ".join(available_subagent_names)
        return f"Error: Unknown subagent type '{subagent_type}'. Available: {available}"

    overrides: dict = {}

    skills_section = get_skills_prompt_section()
    if skills_section:
        overrides["system_prompt"] = config.system_prompt + "\n\n" + skills_section

    if overrides:
        config = replace(config, **overrides)
    config = _apply_max_turns_override(
        config,
        subagent_type=subagent_type,
        requested_max_turns=max_turns,
    )

    sandbox_state = None
    thread_data = None
    thread_id = None
    parent_model = None
    trace_id = None
    compile_state: dict[str, str] = {}

    if runtime is not None:
        sandbox_state = runtime.state.get("sandbox")
        thread_data = runtime.state.get("thread_data")
        thread_id = runtime.context.get("thread_id") if runtime.context else None
        if thread_id is None:
            thread_id = runtime.config.get("configurable", {}).get("thread_id")

        metadata = runtime.config.get("metadata", {})
        parent_model = metadata.get("model_name")
        trace_id = metadata.get("trace_id") or str(uuid.uuid4())[:8]
        compile_state = _get_compile_state(runtime)

    from deerflow.tools.tools import get_subagent_tools

    if subagent_type == "compiler":
        from deerflow.agents.middlewares.tool_error_handling_middleware import load_bound_session_async
        from deerflow.compile.evidence import get_active_experiment
        from deerflow.tools.bound_compile_tools import get_bound_compile_tools

        session_id = compile_state.get(COMPILE_SESSION_STATE_KEY)
        if not session_id:
            return 'Error: No compile session is currently bound for compiler subagent. Call prepare_compile_session(), then clone_repository(), then identify_build_system(), then task(..., subagent_type="compiler").'
        if not thread_id:
            return "Error: Missing thread_id for compiler subagent execution."

        session = await load_bound_session_async(session_id=session_id, thread_id=thread_id)
        tools = get_bound_compile_tools(session)
        active = get_active_experiment(thread_id)
        if active is not None:
            config = config.with_overrides(
                max_turns=active.policy.compiler_max_turns,
                timeout_seconds=active.policy.subagent_timeout_seconds,
            )
            prompt = _with_benchmark_constraints(prompt, active.policy)
    else:
        tools = get_subagent_tools(subagent_type=subagent_type, model_name=parent_model)

    executor = SubagentExecutor(
        config=config,
        tools=tools,
        parent_model=parent_model,
        sandbox_state=sandbox_state,
        thread_data=thread_data,
        thread_id=thread_id,
        trace_id=trace_id,
        initial_state=compile_state,
    )

    task_id = executor.execute_async(prompt, task_id=tool_call_id)

    poll_count = 0
    last_status = None
    last_message_count = 0
    max_poll_count = (config.timeout_seconds + 60) // 5
    shutdown_timeout_seconds = max(30.0, min(float(config.timeout_seconds), 180.0))

    logger.info(f"[trace={trace_id}] Started background task {task_id} (subagent={subagent_type}, timeout={config.timeout_seconds}s, polling_limit={max_poll_count} polls)")

    writer = get_stream_writer()
    writer({"type": "task_started", "task_id": task_id, "description": description})

    try:
        while True:
            result = get_background_task_result(task_id)

            if result is None:
                logger.error(f"[trace={trace_id}] Task {task_id} not found in background tasks")
                writer({"type": "task_failed", "task_id": task_id, "error": "Task disappeared from background tasks"})
                await _cancel_and_reap_task(
                    task_id=task_id,
                    subagent_type=subagent_type,
                    compile_state=compile_state,
                    thread_id=thread_id,
                    terminal_status="failed",
                    error="Compiler task disappeared from background task tracking.",
                    shutdown_timeout_seconds=shutdown_timeout_seconds,
                )
                return f"Error: Task {task_id} disappeared from background tasks"

            if result.status != last_status:
                logger.info(f"[trace={trace_id}] Task {task_id} status: {result.status.value}")
                last_status = result.status

            current_message_count = len(result.ai_messages)
            if current_message_count > last_message_count:
                for i in range(last_message_count, current_message_count):
                    message = result.ai_messages[i]
                    writer(
                        {
                            "type": "task_running",
                            "task_id": task_id,
                            "message": message,
                            "message_index": i + 1,
                            "total_messages": current_message_count,
                        }
                    )
                    logger.info(f"[trace={trace_id}] Task {task_id} sent message #{i + 1}/{current_message_count}")
                last_message_count = current_message_count

            if result.status == SubagentStatus.COMPLETED:
                writer({"type": "task_completed", "task_id": task_id, "result": result.result})
                logger.info(f"[trace={trace_id}] Task {task_id} completed after {poll_count} polls")
                cleanup_background_task(task_id)
                return f"Task Succeeded. Result: {result.result}"
            elif result.status == SubagentStatus.FAILED:
                writer({"type": "task_failed", "task_id": task_id, "error": result.error})
                logger.error(f"[trace={trace_id}] Task {task_id} failed: {result.error}")
                await _cancel_and_reap_task(
                    task_id=task_id,
                    subagent_type=subagent_type,
                    compile_state=compile_state,
                    thread_id=thread_id,
                    terminal_status="failed",
                    error=result.error or "Compiler task failed.",
                    shutdown_timeout_seconds=shutdown_timeout_seconds,
                )
                return f"Task failed. Error: {result.error}"
            elif result.status == SubagentStatus.CANCELLED:
                writer({"type": "task_cancelled", "task_id": task_id, "error": result.error})
                logger.info(f"[trace={trace_id}] Task {task_id} cancelled: {result.error}")
                await _cancel_and_reap_task(
                    task_id=task_id,
                    subagent_type=subagent_type,
                    compile_state=compile_state,
                    thread_id=thread_id,
                    terminal_status="cancelled",
                    error=result.error or "Compiler task cancelled by user.",
                    shutdown_timeout_seconds=shutdown_timeout_seconds,
                )
                return "Task cancelled by user."
            elif result.status == SubagentStatus.TIMED_OUT:
                writer({"type": "task_timed_out", "task_id": task_id, "error": result.error})
                logger.warning(f"[trace={trace_id}] Task {task_id} timed out: {result.error}")
                await _cancel_and_reap_task(
                    task_id=task_id,
                    subagent_type=subagent_type,
                    compile_state=compile_state,
                    thread_id=thread_id,
                    terminal_status="timed_out",
                    error=result.error or "Compiler task timed out.",
                    shutdown_timeout_seconds=shutdown_timeout_seconds,
                )
                return f"Task timed out. Error: {result.error}"

            await asyncio.sleep(5)
            poll_count += 1

            if poll_count > max_poll_count:
                timeout_minutes = config.timeout_seconds // 60
                logger.error(f"[trace={trace_id}] Task {task_id} polling timed out after {poll_count} polls (should have been caught by thread pool timeout)")
                writer({"type": "task_timed_out", "task_id": task_id})
                await _cancel_and_reap_task(
                    task_id=task_id,
                    subagent_type=subagent_type,
                    compile_state=compile_state,
                    thread_id=thread_id,
                    terminal_status="timed_out",
                    error=f"Compiler task polling timed out after {timeout_minutes} minutes.",
                    shutdown_timeout_seconds=shutdown_timeout_seconds,
                )
                return f"Task polling timed out after {timeout_minutes} minutes. This may indicate the background task is stuck. Status: {result.status.value}"
    except asyncio.CancelledError:
        await _cancel_and_reap_task(
            task_id=task_id,
            subagent_type=subagent_type,
            compile_state=compile_state,
            thread_id=thread_id,
            terminal_status="cancelled",
            error="Compiler task cancelled with its parent run.",
            shutdown_timeout_seconds=shutdown_timeout_seconds,
        )
        raise

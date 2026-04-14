from __future__ import annotations

from deerflow.compile.operations import (
    clone_repository_impl,
    finalize_compile_session_impl,
    inspect_build_system_impl,
    prepare_compile_session_impl,
    relative_or_original,
    run_compile_command_impl,
    verify_build_artifacts_impl,
)
from deerflow.compile.workflow.build_agent import BuildAgentInput, BuildDecisionAgent
from deerflow.compile.workflow.schemas import BuildAttempt, CompileWorkflowInput, CompileWorkflowState


def run_prepare_stage(state: CompileWorkflowState, workflow_input: CompileWorkflowInput):
    session = prepare_compile_session_impl(
        thread_id=workflow_input.thread_id,
        repo_url=workflow_input.repo_url,
        branch=workflow_input.branch,
        task_description=workflow_input.task_description,
        owner_id=workflow_input.owner_id,
    )
    state.session_id = session.session_id
    state.status = "ready"
    state.prepare_done = True
    return session



def run_clone_stage(state: CompileWorkflowState, workflow_input: CompileWorkflowInput, session) -> None:
    _, message = clone_repository_impl(
        session=session,
        repo_url=workflow_input.repo_url,
        branch=workflow_input.branch,
    )
    state.clone_done = True
    state.status = "source_ready"
    state.summary = message



def run_inspect_stage(state: CompileWorkflowState, session) -> list[str]:
    primary_system, _, suggested_commands = inspect_build_system_impl(session=session)
    state.build_system = primary_system
    state.inspect_done = True
    state.status = "inspected"
    return suggested_commands



def run_build_stage(state: CompileWorkflowState, session, workflow_input: CompileWorkflowInput) -> None:
    if not state.build_system:
        raise RuntimeError("Build system not detected before build stage")

    agent = BuildDecisionAgent()
    latest_failure_summary: str | None = None
    state.status = "building"

    for _ in range(workflow_input.max_build_attempts):
        decision = agent.next_decision(
            BuildAgentInput(
                repo_url=workflow_input.repo_url,
                build_system=state.build_system,
                task_description=workflow_input.task_description,
                artifact_hint=workflow_input.artifact_hint,
                build_goal=workflow_input.build_goal,
                previous_attempts=[attempt.__dict__ for attempt in state.attempts],
                latest_failure_summary=latest_failure_summary,
                max_build_attempts=workflow_input.max_build_attempts,
            )
        )

        if decision.should_stop:
            raise RuntimeError(decision.rationale or "Build agent decided to stop")
        if not decision.command:
            raise RuntimeError("Build agent did not provide a command")

        result, record, message = run_compile_command_impl(
            session=session,
            command=decision.command,
            stage=decision.stage,
        )
        attempt_summary = f"{decision.rationale} | {message}" if decision.rationale else message
        state.attempts.append(BuildAttempt.from_command_record(record, summary=attempt_summary))
        if record.log_path:
            state.logs.append(relative_or_original(session, record.log_path))

        if result.exit_code == 0:
            state.build_done = True
            state.summary = attempt_summary
            return

        latest_failure_summary = attempt_summary

    raise RuntimeError(f"Build failed after {workflow_input.max_build_attempts} attempts")



def run_verify_stage(state: CompileWorkflowState, session, workflow_input: CompileWorkflowInput) -> None:
    _, artifacts, message = verify_build_artifacts_impl(
        session=session,
        file_pattern=workflow_input.artifact_hint,
    )
    state.verify_done = True
    state.verify_message = message
    state.artifacts = artifacts
    if not artifacts:
        state.summary = message
        raise RuntimeError(message)
    state.status = "artifacts_verified"
    state.summary = message



def run_finalize_stage(state: CompileWorkflowState, session, workflow_input: CompileWorkflowInput) -> None:
    response = finalize_compile_session_impl(
        session=session,
        summary=state.summary,
        generate_repro_bundle=workflow_input.generate_repro_bundle,
    )
    state.finalized = True
    state.logs = response.get("logs", [])
    state.repro_files = response.get("repro_files", [])

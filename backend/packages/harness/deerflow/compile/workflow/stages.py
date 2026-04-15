from __future__ import annotations

from deerflow.compile.operations import (
    clone_repository_impl,
    finalize_compile_session_impl,
    inspect_build_system_impl,
    prepare_compile_session_impl,
    record_build_artifact_impl,
    relative_or_original,
    verify_build_artifacts_impl,
)
from deerflow.compile.workflow.build_subagent_runner import run_build_subagent_once
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
    result, message = clone_repository_impl(
        session=session,
        repo_url=workflow_input.repo_url,
        branch=workflow_input.branch,
    )
    state.clone_done = True
    state.summary = message
    if result.exit_code != 0:
        state.status = "failed"
        state.error = result.combined_output[:4000] or message
        raise RuntimeError(message)
    state.status = "source_ready"


def run_inspect_stage(state: CompileWorkflowState, session) -> list[str]:
    primary_system, _, suggested_commands = inspect_build_system_impl(session=session)
    state.build_system = primary_system
    state.inspect_done = True
    state.status = "inspected"
    return suggested_commands


def run_build_stage(state: CompileWorkflowState, session, workflow_input: CompileWorkflowInput) -> None:
    if not state.build_system:
        raise RuntimeError("Build system not detected before build stage")

    from deerflow.compile.operations import get_compile_services

    services = get_compile_services()
    state.status = "building"
    previous_command_count = len(session.commands)
    previous_artifact_count = len(session.artifacts)
    services.manager.log_event(
        session,
        "build.subagent.started",
        build_system=state.build_system,
        previous_command_count=previous_command_count,
    )
    execution = run_build_subagent_once(
        session=session,
        workflow_input=workflow_input,
        build_system=state.build_system,
    )

    session = services.manager.load_session(session.session_id, session.thread_id)
    new_records = session.commands[previous_command_count:]
    for record in new_records:
        attempt = BuildAttempt.from_command_record(record)
        state.attempts.append(attempt)
        if record.log_path:
            state.logs.append(relative_or_original(session, record.log_path))

    services.manager.log_event(
        session,
        "build.subagent.completed",
        subagent_status=execution.subagent_status.value,
        parsed=execution.parsed_result is not None,
        new_command_count=len(new_records),
        raw_output=execution.raw_output,
        error=execution.error,
    )

    if execution.subagent_status.value != "completed":
        state.error = execution.error or execution.raw_output or "Build subagent failed"
        raise RuntimeError(state.error)

    if execution.parsed_result is None:
        state.error = execution.error or execution.raw_output or "Build subagent result could not be parsed"
        raise RuntimeError(state.error)

    state.summary = execution.parsed_result.summary
    if execution.parsed_result.build_status == "success" and execution.parsed_result.proceed_to_verify:
        for artifact_path in execution.parsed_result.artifacts:
            record_build_artifact_impl(session=session, artifact_path=artifact_path)
        session = services.manager.load_session(session.session_id, session.thread_id)
        state.artifacts = session.artifacts[previous_artifact_count:]
        state.build_done = True
        state.status = "build_completed"
        return

    state.error = execution.parsed_result.summary
    raise RuntimeError(execution.parsed_result.summary)


def run_verify_stage(state: CompileWorkflowState, session, workflow_input: CompileWorkflowInput) -> None:
    _, artifacts, message = verify_build_artifacts_impl(
        session=session,
        file_pattern=workflow_input.artifact_hint,
        copy_to_artifacts=False,
    )
    state.verify_done = True
    state.verify_message = message
    state.artifacts = artifacts
    state.status = "artifacts_verified"


def run_finalize_stage(state: CompileWorkflowState, session, workflow_input: CompileWorkflowInput) -> None:
    updated_session = finalize_compile_session_impl(
        session=session,
        summary=state.summary,
        status=state.status,
        generate_repro_bundle=workflow_input.generate_repro_bundle,
    )
    state.finalized = True
    state.logs = [
        relative_or_original(updated_session, command.log_path)
        for command in updated_session.commands
        if command.log_path
    ]
    workflow_log = relative_or_original(updated_session, updated_session.metadata_file.parent / "logs" / "workflow.log")
    if workflow_log not in state.logs:
        state.logs.append(workflow_log)
    repro_dir = updated_session.metadata_file.parent / "repro"
    build_script = repro_dir / "build.sh"
    state.repro_files = [relative_or_original(updated_session, build_script)] if build_script.exists() else []

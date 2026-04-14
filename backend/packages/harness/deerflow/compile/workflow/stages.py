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
from deerflow.compile.workflow.schemas import BuildAttempt, CompileWorkflowInput, CompileWorkflowState


_DEFAULT_BUILD_COMMANDS = {
    "cmake": [("configure", "mkdir -p build && cd build && cmake .."), ("build", "cmake --build build -j")],
    "make": [("build", "make -j")],
    "cargo": [("build", "cargo build --release")],
    "npm": [("install", "npm install"), ("build", "npm run build")],
    "go": [("build", "go build ./...")],
    "python": [("build", "python -m build")],
    "python-legacy": [("build", "python setup.py build")],
}


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



def run_placeholder_build_stage(state: CompileWorkflowState, session) -> None:
    if not state.build_system:
        raise RuntimeError("Build system not detected before build stage")

    commands = _DEFAULT_BUILD_COMMANDS.get(state.build_system)
    if not commands:
        raise RuntimeError(f"No default build commands available for build system: {state.build_system}")

    state.status = "building"
    for stage_name, command in commands:
        result, record, message = run_compile_command_impl(
            session=session,
            command=command,
            stage=stage_name,
        )
        state.attempts.append(BuildAttempt.from_command_record(record, summary=message))
        if record.log_path:
            state.logs.append(relative_or_original(session, record.log_path))
        if result.exit_code != 0:
            raise RuntimeError(message)

    state.build_done = True



def run_verify_stage(state: CompileWorkflowState, session, workflow_input: CompileWorkflowInput) -> None:
    _, artifacts, message = verify_build_artifacts_impl(
        session=session,
        file_pattern=workflow_input.artifact_hint,
    )
    state.verify_done = True
    state.artifacts = artifacts
    if not artifacts:
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


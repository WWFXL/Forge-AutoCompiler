from __future__ import annotations

from deerflow.compile.operations import get_bound_session, get_compile_services
from deerflow.compile.workflow.schemas import CompileWorkflowInput, CompileWorkflowResult, CompileWorkflowState
from deerflow.compile.workflow.stages import (
    run_build_stage,
    run_clone_stage,
    run_finalize_stage,
    run_inspect_stage,
    run_prepare_stage,
    run_verify_stage,
)


class CompileWorkflowRunner:
    def run(self, workflow_input: CompileWorkflowInput) -> CompileWorkflowResult:
        state = self._init_state(workflow_input)
        session = None
        services = get_compile_services()

        try:
            session = run_prepare_stage(state, workflow_input)
            services.manager.log_event(session, "workflow.stage.started", stage="clone")
            run_clone_stage(state, workflow_input, session)
            services.manager.log_event(session, "workflow.stage.completed", stage="clone", status=state.status)
            services.manager.log_event(session, "workflow.stage.started", stage="inspect")
            run_inspect_stage(state, session)
            services.manager.log_event(session, "workflow.stage.completed", stage="inspect", status=state.status, build_system=state.build_system)
            services.manager.log_event(session, "workflow.stage.started", stage="build")
            run_build_stage(state, session, workflow_input)
            services.manager.log_event(session, "workflow.stage.completed", stage="build", status=state.status, attempts=len(state.attempts))
            services.manager.log_event(session, "workflow.stage.started", stage="verify")
            run_verify_stage(state, session, workflow_input)
            services.manager.log_event(session, "workflow.stage.completed", stage="verify", status=state.status, artifact_count=len(state.artifacts))
            state.status = "completed"
        except Exception as exc:
            state.status = "failed"
            state.error = str(exc)
            if not state.summary:
                state.summary = str(exc)
            if session is not None:
                services.manager.log_event(
                    session,
                    "workflow.failed",
                    error=str(exc),
                    summary=state.summary,
                    status=state.status,
                )
        finally:
            if session is None and state.session_id:
                session = get_bound_session(state.session_id, state.thread_id, state.owner_id)
            if session is not None:
                services.manager.log_event(
                    session,
                    "workflow.finalizing",
                    status=state.status,
                    summary=state.summary,
                    error=state.error,
                )
                run_finalize_stage(state, session, workflow_input)

        return self._to_result(state)

    def _init_state(self, workflow_input: CompileWorkflowInput) -> CompileWorkflowState:
        return CompileWorkflowState(
            thread_id=workflow_input.thread_id,
            repo_url=workflow_input.repo_url,
            branch=workflow_input.branch,
            task_description=workflow_input.task_description,
            artifact_hint=workflow_input.artifact_hint,
            build_goal=workflow_input.build_goal,
            owner_id=workflow_input.owner_id,
        )

    def _to_result(self, state: CompileWorkflowState) -> CompileWorkflowResult:
        artifact_paths = [artifact.path for artifact in state.artifacts]
        if state.status == "completed":
            default_summary = "Compile workflow completed with verified artifacts"
        elif state.build_done and not artifact_paths:
            default_summary = "Build commands succeeded, but no matching artifacts were found"
        else:
            default_summary = "Compile workflow failed"

        return CompileWorkflowResult(
            status=state.status,
            summary=state.summary or default_summary,
            session_id=state.session_id,
            build_system=state.build_system,
            attempts=state.attempts,
            artifacts=artifact_paths,
            logs=state.logs,
            repro_files=state.repro_files,
            verify_message=state.verify_message,
            error=state.error,
        )

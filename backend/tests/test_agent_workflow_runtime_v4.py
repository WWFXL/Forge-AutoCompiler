from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import time
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import Field

from deerflow.compile.agent_workflow_runtime import AgentWorkflowBudgetTracker
from deerflow.compile.agent_workflow_runtime_v4 import (
    ProgressAwareHarnessMiddleware,
    build_progress_snapshot,
    compact_model_messages,
    run_agent_workflow_node_v4,
)
from deerflow.compile.agent_workflow_schemas import (
    AgentBuildNodeInput,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
)
from deerflow.compile.candidate_verifier import FunctionalCheckEvidence
from deerflow.compile.external_evaluator import FunctionalOracleSpec
from deerflow.compile.schemas import BuildCommandRecord, CompileSession, utc_now_iso

SHA256_A = "a" * 64
SHA256_B = "b" * 64
SHA256_C = "c" * 64
COMMIT_SHA = "d" * 40


class FakeManager:
    def __init__(self, session: CompileSession):
        self.session = session

    def load_session(self, session_id: str, thread_id: str | None = None) -> CompileSession:
        assert session_id == self.session.session_id
        assert thread_id == self.session.thread_id
        return self.session


class RecordingLedger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def append(self, event_type: str, **payload: Any) -> None:
        self.events.append((event_type, payload))


class PassingFunctionalRunner:
    def run(self, *, spec: FunctionalOracleSpec, session: CompileSession, manager: Any) -> FunctionalCheckEvidence:
        del session, manager
        return FunctionalCheckEvidence(
            oracle_ref=spec.oracle_ref,
            passed=True,
            command_id="command-oracle",
            exit_code=0,
            timed_out=False,
            stdout_sha256=hashlib.sha256(b"ok").hexdigest(),
            stderr_sha256=hashlib.sha256(b"").hexdigest(),
        )


class CapturingScriptedModel(BaseChatModel):
    responses: list[AIMessage]
    calls: int = 0
    messages_seen: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "progress-harness-scripted-zero-provider"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        del tools, tool_choice, kwargs
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        self.messages_seen.append(messages)
        response = self.responses[self.calls]
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=response)])


def _tool_call(name: str, args: dict[str, Any], call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
        usage_metadata={"input_tokens": 7, "output_tokens": 5, "total_tokens": 12},
    )


def _budget() -> AgentWorkflowBudget:
    return AgentWorkflowBudget(
        max_model_requests=8,
        max_recorded_tokens=1_000,
        max_agent_steps=24,
        max_tool_calls=16,
        max_commands=8,
        node_timeout_seconds=600,
        command_timeout_seconds=300,
        evaluator_timeout_seconds=600,
        replay_timeout_seconds=1_200,
        cleanup_timeout_seconds=120,
    )


def _session(tmp_path: Path) -> CompileSession:
    session_dir = tmp_path / "thread-v4" / "session-v4"
    artifacts_dir = session_dir / "artifacts"
    artifacts_dir.joinpath("bin").mkdir(parents=True)
    shutil.copy2("/bin/true", artifacts_dir / "bin" / "tool")
    now = utc_now_iso()
    commands = [
        BuildCommandRecord(
            stage="bash",
            command="./autogen.sh",
            workdir="/workspace/repo",
            command_id="command-autogen",
            role="dependency",
            completed_at=now,
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="bash",
            command="./configure",
            workdir="/workspace/repo",
            command_id="command-configure",
            role="configure",
            completed_at=now,
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="bash",
            command="make",
            workdir="/workspace/repo",
            command_id="command-build",
            role="build",
            completed_at=now,
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="bash",
            command="cp tool /artifacts/bin/tool",
            workdir="/workspace/repo",
            command_id="command-stage",
            role="artifact_stage",
            completed_at=now,
            exit_code=0,
        ),
    ]
    return CompileSession(
        session_id="session-v4",
        thread_id="thread-v4",
        run_id="run-v4",
        repo_url="https://example.invalid/progress.git",
        branch="main",
        commit_sha=COMMIT_SHA,
        image="autocompiler:test",
        image_id=f"sha256:{'e' * 64}",
        status="inspected",
        selected_build_system="autotools",
        leadagent_repo_dir=str(session_dir / "workspace" / "repo"),
        leadagent_artifacts_dir=str(artifacts_dir),
        leadagent_logs_dir=str(session_dir / "logs"),
        leadagent_repro_dir=str(session_dir / "repro"),
        metadata_path=str(session_dir / "session.json"),
        commands=commands,
    )


def _node_input(session: CompileSession) -> AgentBuildNodeInput:
    return AgentBuildNodeInput(
        task_id="progress-harness-fixture",
        attempt_id="attempt-v4",
        session_id=session.session_id,
        repository_url=session.repo_url,
        commit_sha=session.commit_sha or "",
        source_snapshot_sha256=SHA256_A,
        build_system_candidates=("autotools",),
        target_contract=AgentWorkflowTargetContract(
            target_id="tool-executable",
            artifact_types=("executable",),
            artifact_path_patterns=("bin/tool",),
            functional_oracle_ref="oracle-progress-v1",
        ),
        operation_policy_ref="progress-harness-zero-provider-v1",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=session.image_id or "",
            parallel_jobs=session.parallel_jobs,
            network_policy="none-after-checkpoint",
        ),
        budget=_budget(),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256=SHA256_A,
            protocol_sha256=SHA256_B,
            runner_sha256=SHA256_C,
        ),
        initial_observation={"required_candidate_artifacts": ("bin/tool",), "zero_provider": True},
    )


def _submit_args() -> dict[str, Any]:
    return {
        "candidate_id": "candidate-v4",
        "build_system": "autotools",
        "supporting_command_ids": ["command-build"],
        "artifact_paths": ["bin/tool"],
        "target_mapping": {"tool-executable": "bin/tool"},
        "recipe_command_ids": ["command-autogen", "command-configure", "command-build", "command-stage"],
        "agent_summary": "H1 零 Provider fixture",
        "known_limitations": [],
    }


def _events(session: CompileSession) -> list[dict[str, Any]]:
    path = Path(session.metadata_path).parent / "agent-workflow" / "attempt-v4" / "events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_progress_snapshot_exposes_fresh_replay_closure_without_host_paths(tmp_path: Path) -> None:
    session = _session(tmp_path)

    snapshot = build_progress_snapshot(node_input=_node_input(session), session=session)

    assert snapshot.candidate_ready is True
    assert snapshot.recommended_recipe_command_ids == (
        "command-autogen",
        "command-configure",
        "command-build",
        "command-stage",
    )
    assert snapshot.staged_artifact_paths == ("bin/tool",)
    assert snapshot.recommended_target_mapping == {"tool-executable": "bin/tool"}
    assert str(tmp_path) not in snapshot.canonical_json()


def test_context_compaction_keeps_initial_task_and_last_complete_interactions() -> None:
    messages: list[BaseMessage] = [HumanMessage(content="task")]
    for index in range(3):
        call_id = f"call-{index}"
        messages.extend(
            [
                _tool_call("run_container_bash", {"command": f"echo {index}", "command_role": "diagnostic"}, call_id),
                ToolMessage(content=f"result-{index}", tool_call_id=call_id, name="run_container_bash"),
            ]
        )

    compacted = compact_model_messages(messages, max_model_interactions=2)

    assert compacted[0].content == "task"
    assert [message.tool_call_id for message in compacted if isinstance(message, ToolMessage)] == ["call-1", "call-2"]
    retained_call_ids = {call["id"] for message in compacted if isinstance(message, AIMessage) for call in message.tool_calls}
    assert retained_call_ids == {"call-1", "call-2"}


def test_runtime_v4_blocks_ready_command_then_accepts_strict_candidate(tmp_path: Path) -> None:
    session = _session(tmp_path)
    model = CapturingScriptedModel(
        responses=[
            _tool_call(
                "run_container_bash",
                {
                    "command": "find /artifacts -maxdepth 2 -type f",
                    "command_role": "diagnostic",
                    "timeout_seconds": 10,
                    "workdir": "/workspace/repo",
                },
                "diagnostic-after-ready",
            ),
            _tool_call("submit_candidate_v1", _submit_args(), "submit-after-guard"),
        ]
    )

    result = asyncio.run(
        run_agent_workflow_node_v4(
            node_input=_node_input(session),
            session=session,
            manager=FakeManager(session),  # type: ignore[arg-type]
            model=model,
            oracle_registry={
                "oracle-progress-v1": FunctionalOracleSpec(
                    oracle_ref="oracle-progress-v1",
                    argv=("/bin/true",),
                )
            },
            functional_runner=PassingFunctionalRunner(),
        )
    )

    assert result.node_status == "submitted"
    assert result.candidate_submitted is True
    assert result.usage.model_requests == 2
    assert result.usage.tool_calls == 2
    assert result.usage.commands == 0
    assert len(session.commands) == 4
    assert model.calls == 2
    assert all("<authoritative_compile_progress>" in str(messages[-1].content) for messages in model.messages_seen)
    events = _events(session)
    rejections = [event for event in events if event["event_type"] == "harness.tool_rejected"]
    assert [event["payload"]["reason"] for event in rejections] == ["candidate_ready_requires_submit"]
    assert any(event["event_type"] == "candidate.prefreeze_verification_completed" and event["payload"]["passed"] for event in events)
    assert any(event["event_type"] == "harness.submission_frontier_attempted" for event in events)


def test_rejected_submission_unlocks_only_the_same_progress_frontier(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ledger = RecordingLedger()
    middleware = ProgressAwareHarnessMiddleware(
        node_input=_node_input(session),
        session=session,
        manager=FakeManager(session),  # type: ignore[arg-type]
        tracker=AgentWorkflowBudgetTracker(_budget()),
        ledger=ledger,  # type: ignore[arg-type]
        started_monotonic=time.monotonic(),
    )
    submit = SimpleNamespace(tool_call={"name": "submit_candidate_v1", "args": {}, "id": "rejected-submit"})
    rejected = middleware._wrap_tool_result(
        submit,
        lambda _request: ToolMessage(
            content='{"accepted":false}',
            tool_call_id="rejected-submit",
            name="submit_candidate_v1",
            status="error",
        ),
    )
    assert isinstance(rejected, ToolMessage)

    command = SimpleNamespace(
        tool_call={
            "name": "run_container_bash",
            "args": {"command_role": "build"},
            "id": "repair-command",
        }
    )
    assert middleware._guard_reason(command, middleware.snapshot()) is None

    session.commands.append(
        BuildCommandRecord(
            stage="bash",
            command="cmake --build build",
            workdir="/workspace/repo",
            command_id="command-repair",
            role="build",
            completed_at=utc_now_iso(),
            exit_code=0,
        )
    )
    assert middleware._guard_reason(command, middleware.snapshot()) == "candidate_ready_requires_submit"
    assert [event for event, _payload in ledger.events] == ["harness.submission_frontier_attempted"]


def test_runtime_v4_blocks_fifth_consecutive_diagnostic_without_execution(tmp_path: Path) -> None:
    session = _session(tmp_path)
    Path(session.leadagent_artifacts_dir, "bin", "tool").unlink()
    session.commands = [
        BuildCommandRecord(
            stage="bash",
            command=f"sed -n '{index},10p' CMakeLists.txt",
            workdir="/workspace/repo",
            command_id=f"command-diagnostic-{index}",
            role="diagnostic",
            completed_at=utc_now_iso(),
            exit_code=0,
        )
        for index in range(4)
    ]
    model = CapturingScriptedModel(
        responses=[
            _tool_call(
                "run_container_bash",
                {
                    "command": "sed -n '40,80p' CMakeLists.txt",
                    "command_role": "diagnostic",
                    "timeout_seconds": 10,
                    "workdir": "/workspace/repo",
                },
                "fifth-diagnostic",
            ),
            AIMessage(content="无法在当前边界继续。", usage_metadata={"input_tokens": 4, "output_tokens": 4, "total_tokens": 8}),
        ]
    )

    result = asyncio.run(
        run_agent_workflow_node_v4(
            node_input=_node_input(session),
            session=session,
            manager=FakeManager(session),  # type: ignore[arg-type]
            model=model,
            oracle_registry={
                "oracle-progress-v1": FunctionalOracleSpec(
                    oracle_ref="oracle-progress-v1",
                    argv=("/bin/true",),
                )
            },
            functional_runner=PassingFunctionalRunner(),
        )
    )

    assert result.node_status == "no_submission"
    assert result.usage.tool_calls == 1
    assert result.usage.commands == 0
    assert len(session.commands) == 4
    events = _events(session)
    assert any(event["event_type"] == "harness.tool_rejected" and event["payload"]["reason"] == "diagnostic_no_progress_limit" for event in events)

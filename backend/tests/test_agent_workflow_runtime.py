from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from langchain.tools import tool
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import Field

from deerflow.compile.agent_workflow_node import AgentWorkflowBudgetTracker, AgentWorkflowCandidateStore, AgentWorkflowNodeStatus, AgentWorkflowStateMachine
from deerflow.compile.agent_workflow_runtime import AgentWorkflowCandidateService, AgentWorkflowEvidenceLedger, AgentWorkflowNodeRunner, run_agent_workflow_node_v1
from deerflow.compile.agent_workflow_schemas import (
    AgentBuildNodeInput,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
    SubmitCandidateRequest,
)
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


class ScriptedChatModel(BaseChatModel):
    responses: list[AIMessage]
    calls: int = 0
    bind_kwargs: list[dict[str, Any]] = Field(default_factory=list)
    generate_kwargs: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "agent-workflow-scripted"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        del tools, tool_choice
        self.bind_kwargs.append(kwargs)
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager
        self.generate_kwargs.append(kwargs)
        response = self.responses[self.calls]
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=response)])


class SlowChatModel(ScriptedChatModel):
    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        await asyncio.sleep(2)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="late"))])


def make_budget(**overrides: int | float) -> AgentWorkflowBudget:
    values: dict[str, int | float] = {
        "max_model_requests": 8,
        "max_recorded_tokens": 120_000,
        "max_agent_steps": 24,
        "max_tool_calls": 32,
        "max_commands": 24,
        "node_timeout_seconds": 600,
        "command_timeout_seconds": 300,
        "evaluator_timeout_seconds": 600,
        "replay_timeout_seconds": 1_200,
        "cleanup_timeout_seconds": 120,
    }
    values.update(overrides)
    return AgentWorkflowBudget(**values)  # type: ignore[arg-type]


def make_node_input(session: CompileSession, **overrides: Any) -> AgentBuildNodeInput:
    values = {
        "task_id": "task-fmt",
        "attempt_id": "attempt-001",
        "session_id": session.session_id,
        "repository_url": session.repo_url,
        "commit_sha": session.commit_sha,
        "source_snapshot_sha256": SHA256_A,
        "build_system_candidates": ("cmake",),
        "target_contract": AgentWorkflowTargetContract(
            target_id="fmt-library",
            artifact_types=("static_library",),
            artifact_path_patterns=("lib/libfmt.a",),
            functional_oracle_ref="oracle-fmt-link-v1",
        ),
        "operation_policy_ref": "compile-policy-v1",
        "environment": AgentWorkflowEnvironmentIdentity(
            image_id=session.image_id,
            parallel_jobs=session.parallel_jobs,
            network_policy="compile-network-v1",
        ),
        "budget": make_budget(),
        "experiment_identity": AgentWorkflowExperimentIdentity(
            manifest_sha256=SHA256_A,
            protocol_sha256=SHA256_B,
            runner_sha256=SHA256_C,
        ),
        "initial_observation": {"build_system": "cmake"},
    }
    values.update(overrides)
    return AgentBuildNodeInput(**values)


def make_session(tmp_path: Path) -> CompileSession:
    session_dir = tmp_path / "thread-001" / "session-001"
    artifacts_dir = session_dir / "artifacts"
    artifacts_dir.joinpath("lib").mkdir(parents=True)
    metadata_path = session_dir / "session.json"
    now = utc_now_iso()
    commands = [
        BuildCommandRecord(
            stage="bash",
            command="cmake -S . -B build",
            workdir="/workspace/repo",
            command_id="command-configure",
            role="configure",
            completed_at=now,
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="bash",
            command="cmake --build build",
            workdir="/workspace/repo",
            command_id="command-build",
            role="build",
            completed_at=now,
            exit_code=0,
        ),
        BuildCommandRecord(
            stage="bash",
            command="cp build/libfmt.a /artifacts/lib/libfmt.a",
            workdir="/workspace/repo",
            command_id="command-stage",
            role="artifact_stage",
            completed_at=now,
            exit_code=0,
        ),
    ]
    return CompileSession(
        session_id="session-001",
        thread_id="thread-001",
        repo_url="https://github.com/fmtlib/fmt.git",
        branch="main",
        image="autocompiler:gcc13",
        image_id=f"sha256:{SHA256_B}",
        status="inspected",
        run_id="run-001",
        commit_sha=COMMIT_SHA,
        selected_build_system="cmake",
        metadata_path=str(metadata_path),
        leadagent_repo_dir=str(session_dir / "workspace" / "repo"),
        leadagent_artifacts_dir=str(artifacts_dir),
        leadagent_logs_dir=str(session_dir / "logs"),
        leadagent_repro_dir=str(session_dir / "repro"),
        commands=commands,
    )


def submit_args(**overrides: Any) -> dict[str, Any]:
    values = {
        "candidate_id": "candidate-001",
        "build_system": "cmake",
        "supporting_command_ids": ["command-build"],
        "artifact_paths": ["lib/libfmt.a"],
        "target_mapping": {"fmt-library": "lib/libfmt.a"},
        "recipe_command_ids": ["command-configure", "command-build", "command-stage"],
        "agent_summary": "已生成候选。",
        "known_limitations": [],
    }
    values.update(overrides)
    return values


def test_task_prompt_exposes_frozen_target_policy_and_initial_observation(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    runner = AgentWorkflowNodeRunner(
        node_input=make_node_input(session),
        session=session,
        manager=FakeManager(session),  # type: ignore[arg-type]
        model=ScriptedChatModel(responses=[]),
    )

    prompt = runner._task_prompt()

    assert '"target_id":"fmt-library"' in prompt
    assert '"artifact_types":["static_library"]' in prompt
    assert '"artifact_path_patterns":["lib/libfmt.a"]' in prompt
    assert '"functional_oracle_ref":"oracle-fmt-link-v1"' in prompt
    assert '"operation_policy_ref":"compile-policy-v1"' in prompt
    assert '"initial_observation":{"build_system":"cmake"}' in prompt


def tool_call_message(name: str, args: dict[str, Any], call_id: str, *, total_tokens: int = 15) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
        usage_metadata={"input_tokens": max(0, total_tokens - 5), "output_tokens": min(5, total_tokens), "total_tokens": total_tokens},
    )


def read_events(session: CompileSession, attempt_id: str = "attempt-001") -> list[dict[str, Any]]:
    path = Path(session.metadata_path).parent / "agent-workflow" / attempt_id / "events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_accepted_submit_stops_before_second_model_request_and_disables_parallel_tools(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    Path(session.leadagent_artifacts_dir, "lib", "libfmt.a").write_bytes(b"archive")
    model = ScriptedChatModel(
        responses=[
            tool_call_message("submit_candidate_v1", submit_args(), "submit-1"),
            AIMessage(content="不应请求第二次模型。"),
        ]
    )

    result = asyncio.run(
        run_agent_workflow_node_v1(
            node_input=make_node_input(session),
            session=session,
            manager=FakeManager(session),  # type: ignore[arg-type]
            model=model,
        )
    )

    assert result.node_status == "submitted"
    assert result.candidate_submitted is True
    assert result.primary_failure is None
    assert model.calls == 1
    assert any(call.get("parallel_tool_calls") is False for call in model.bind_kwargs)
    events = read_events(session)
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    previous_hash = "0" * 64
    for event in events:
        event_hash = event.pop("event_hash")
        assert event["previous_hash"] == previous_hash
        canonical = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        assert event_hash == hashlib.sha256(canonical.encode()).hexdigest()
        previous_hash = event_hash
    assert result.evidence_head_sha256 == previous_hash
    assert {event["payload"]["phase"] for event in events if event["event_type"] == "artifact.observed"} == {"pre_submit", "frozen"}


def test_invalid_submit_can_be_repaired_on_next_model_request(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    Path(session.leadagent_artifacts_dir, "lib", "libfmt.a").write_bytes(b"archive")
    model = ScriptedChatModel(
        responses=[
            tool_call_message("submit_candidate_v1", submit_args(artifact_paths=["/artifacts/libfmt.a"]), "submit-invalid"),
            tool_call_message("submit_candidate_v1", submit_args(), "submit-valid"),
        ]
    )

    result = asyncio.run(
        run_agent_workflow_node_v1(
            node_input=make_node_input(session),
            session=session,
            manager=FakeManager(session),  # type: ignore[arg-type]
            model=model,
        )
    )

    assert result.node_status == "submitted"
    assert model.calls == 2
    rejections = [event for event in read_events(session) if event["event_type"] == "candidate.submit_rejected"]
    assert rejections[0]["payload"]["rejection_codes"] == ["invalid_contract"]


def test_existing_artifact_without_submit_is_no_submission(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    Path(session.leadagent_artifacts_dir, "lib", "libfmt.a").write_bytes(b"archive")
    finalized: list[str] = []
    model = ScriptedChatModel(responses=[AIMessage(content="没有提交候选。")])

    result = asyncio.run(
        run_agent_workflow_node_v1(
            node_input=make_node_input(session),
            session=session,
            manager=FakeManager(session),  # type: ignore[arg-type]
            model=model,
            finalizer=lambda current: finalized.append(current.session_id),
        )
    )

    assert result.node_status == "no_submission"
    assert result.candidate_generated_observed is True
    assert result.candidate_submitted is False
    assert finalized == [session.session_id]


def test_candidate_persistence_failure_never_exposes_submission_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = make_session(tmp_path)
    Path(session.leadagent_artifacts_dir, "lib", "libfmt.a").write_bytes(b"archive")
    model = ScriptedChatModel(responses=[tool_call_message("submit_candidate_v1", submit_args(), "submit-1")])

    def fail_persistence(self: AgentWorkflowCandidateService, request: SubmitCandidateRequest) -> None:
        del self, request
        raise OSError("disk full")

    monkeypatch.setattr(AgentWorkflowCandidateService, "_persist_candidate", fail_persistence)
    result = asyncio.run(
        run_agent_workflow_node_v1(
            node_input=make_node_input(session),
            session=session,
            manager=FakeManager(session),  # type: ignore[arg-type]
            model=model,
        )
    )

    assert result.node_status == "failed"
    assert result.candidate_submitted is False
    assert result.submission_id is None
    assert result.candidate_record_sha256 is None
    assert result.primary_failure == "candidate_persistence_failed"


def test_finalizer_failure_is_secondary_and_node_reaches_one_terminal_state(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    model = ScriptedChatModel(responses=[AIMessage(content="没有候选。")])

    def fail_finalizer(current: CompileSession) -> None:
        del current
        raise RuntimeError("cleanup failed")

    runner = AgentWorkflowNodeRunner(
        node_input=make_node_input(session),
        session=session,
        manager=FakeManager(session),  # type: ignore[arg-type]
        model=model,
        finalizer=fail_finalizer,
    )
    result = asyncio.run(runner.run())

    assert result.node_status == "no_submission"
    assert result.secondary_failures == ("finalizer_failed",)
    assert runner.state_machine.status is AgentWorkflowNodeStatus.COMPLETED


def test_wall_clock_timeout_is_enforced_by_async_timeout(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    model = SlowChatModel(responses=[])

    result = asyncio.run(
        run_agent_workflow_node_v1(
            node_input=make_node_input(session, budget=make_budget(node_timeout_seconds=1)),
            session=session,
            manager=FakeManager(session),  # type: ignore[arg-type]
            model=model,
        )
    )

    assert result.node_status == "no_submission"
    assert result.primary_failure == "budget_exhausted"
    assert result.budget_terminal_reason == "node_timeout_seconds"
    assert result.wall_clock_ms >= 1_000


@pytest.mark.parametrize(
    ("budget", "responses", "expected_reason"),
    [
        (
            make_budget(max_model_requests=1),
            [
                tool_call_message("submit_candidate_v1", submit_args(artifact_paths=["/invalid"]), "invalid-1"),
                tool_call_message("submit_candidate_v1", submit_args(), "valid-1"),
            ],
            "model_requests",
        ),
        (
            make_budget(max_recorded_tokens=10),
            [tool_call_message("submit_candidate_v1", submit_args(), "submit-1", total_tokens=11)],
            "recorded_tokens",
        ),
        (
            make_budget(max_tool_calls=1),
            [
                tool_call_message("submit_candidate_v1", submit_args(artifact_paths=["/invalid"]), "invalid-1"),
                tool_call_message("submit_candidate_v1", submit_args(), "valid-1"),
            ],
            "tool_calls",
        ),
    ],
)
def test_runtime_budget_exhaustion_has_stable_reason(
    tmp_path: Path,
    budget: AgentWorkflowBudget,
    responses: list[AIMessage],
    expected_reason: str,
) -> None:
    session = make_session(tmp_path)
    Path(session.leadagent_artifacts_dir, "lib", "libfmt.a").write_bytes(b"archive")
    model = ScriptedChatModel(responses=responses)

    result = asyncio.run(
        run_agent_workflow_node_v1(
            node_input=make_node_input(session, budget=budget),
            session=session,
            manager=FakeManager(session),  # type: ignore[arg-type]
            model=model,
        )
    )

    assert result.node_status == "no_submission"
    assert result.primary_failure == "budget_exhausted"
    assert result.budget_terminal_reason == expected_reason
    assert result.candidate_submitted is False


def make_service(tmp_path: Path, session: CompileSession) -> AgentWorkflowCandidateService:
    node_input = make_node_input(session)
    tracker = AgentWorkflowBudgetTracker(node_input.budget)
    store = AgentWorkflowCandidateStore(AgentWorkflowStateMachine(status=AgentWorkflowNodeStatus.RUNNING), tracker)
    ledger = AgentWorkflowEvidenceLedger(tmp_path / "service-events.jsonl", node_input=node_input, run_id=session.run_id or "")
    return AgentWorkflowCandidateService(
        node_input=node_input,
        session=session,
        manager=FakeManager(session),  # type: ignore[arg-type]
        store=store,
        candidate_path=tmp_path / "candidate.json",
        ledger=ledger,
    )


def make_request(**overrides: Any) -> SubmitCandidateRequest:
    values = submit_args(**overrides)
    return SubmitCandidateRequest(
        candidate_id=values["candidate_id"],
        build_system=values["build_system"],
        supporting_command_ids=tuple(values["supporting_command_ids"]),
        artifact_paths=tuple(values["artifact_paths"]),
        target_mapping=values["target_mapping"],
        recipe_command_ids=tuple(values["recipe_command_ids"]),
        agent_summary=values["agent_summary"],
        known_limitations=tuple(values["known_limitations"]),
    )


@pytest.mark.parametrize(
    ("request_overrides", "command_mutation", "expected_code"),
    [
        ({"supporting_command_ids": ["command-other"], "recipe_command_ids": ["command-configure", "command-other", "command-stage"]}, None, "command_missing"),
        ({}, ("command-build", "exit_code", 1), "command_not_successful"),
        ({"recipe_command_ids": ["command-build", "command-configure", "command-stage"]}, None, "command_order_invalid"),
        ({}, ("command-stage", "role", "diagnostic"), "command_role_invalid"),
        ({"build_system": "make"}, None, "build_system_mismatch"),
    ],
)
def test_submit_rejects_stale_or_invalid_command_evidence(
    tmp_path: Path,
    request_overrides: dict[str, Any],
    command_mutation: tuple[str, str, Any] | None,
    expected_code: str,
) -> None:
    session = make_session(tmp_path)
    Path(session.leadagent_artifacts_dir, "lib", "libfmt.a").write_bytes(b"archive")
    if command_mutation is not None:
        command_id, field_name, value = command_mutation
        command = next(item for item in session.commands if item.command_id == command_id)
        setattr(command, field_name, value)

    response = make_service(tmp_path, session).submit(make_request(**request_overrides))

    assert response.accepted is False
    assert expected_code in response.rejection_codes


@pytest.mark.parametrize(
    ("prepare_artifact", "expected_code"),
    [
        (lambda path: None, "artifact_missing"),
        (lambda path: path.mkdir(), "artifact_not_regular"),
        (lambda path: path.symlink_to(path.parent / "target"), "artifact_symlink"),
    ],
)
def test_submit_rejects_invalid_artifact(
    tmp_path: Path,
    prepare_artifact: Any,
    expected_code: str,
) -> None:
    session = make_session(tmp_path)
    artifact = Path(session.leadagent_artifacts_dir, "lib", "libfmt.a")
    if expected_code == "artifact_symlink":
        artifact.parent.joinpath("target").write_bytes(b"archive")
    prepare_artifact(artifact)

    response = make_service(tmp_path, session).submit(make_request())

    assert response.accepted is False
    assert expected_code in response.rejection_codes


def test_candidate_file_and_identity_are_frozen_once(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    Path(session.leadagent_artifacts_dir, "lib", "libfmt.a").write_bytes(b"archive")
    service = make_service(tmp_path, session)

    first = service.submit(make_request())
    second = service.submit(make_request(candidate_id="candidate-002"))

    assert first.accepted is True
    assert second.accepted is False
    assert second.rejection_codes == ("candidate_already_frozen",)
    assert second.terminal_for_agent is True
    candidate_path = tmp_path / "candidate.json"
    assert candidate_path.read_text(encoding="utf-8") == make_request().canonical_json()


def test_new_session_command_is_recorded_in_node_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = make_session(tmp_path)
    manager = FakeManager(session)
    Path(session.leadagent_artifacts_dir, "lib", "libfmt.a").write_bytes(b"archive")

    @tool("run_container_bash", parse_docstring=True)
    def fake_run_container_bash(command: str, command_role: str, timeout_seconds: int = 1200, workdir: str | None = None) -> str:
        """记录一条假命令。

        Args:
            command: 命令。
            command_role: 命令角色。
            timeout_seconds: 超时秒数。
            workdir: 工作目录。
        """
        del timeout_seconds
        manager.session.commands.append(
            BuildCommandRecord(
                stage="bash",
                command=command,
                workdir=workdir or "/workspace/repo",
                command_id="command-diagnostic",
                role=command_role,
                completed_at=utc_now_iso(),
                exit_code=0,
            )
        )
        return "command_id=command-diagnostic\nexit_code=0"

    @tool("submit_build_result")
    def unused_submit_build_result() -> str:
        """不会被调用。"""
        return "unused"

    monkeypatch.setattr(
        "deerflow.compile.agent_workflow_runtime.get_bound_compile_tools",
        lambda current: [fake_run_container_bash, unused_submit_build_result],
    )
    model = ScriptedChatModel(
        responses=[
            tool_call_message(
                "run_container_bash",
                {"command": "test -f CMakeLists.txt", "command_role": "diagnostic", "timeout_seconds": 10, "workdir": "/workspace/repo"},
                "run-1",
            ),
            tool_call_message("submit_candidate_v1", submit_args(), "submit-1"),
        ]
    )

    result = asyncio.run(
        run_agent_workflow_node_v1(
            node_input=make_node_input(session),
            session=session,
            manager=manager,  # type: ignore[arg-type]
            model=model,
        )
    )

    assert result.node_status == "submitted"
    command_events = [event for event in read_events(session) if event["event_type"] == "command.completed"]
    assert [event["payload"]["command_id"] for event in command_events] == ["command-diagnostic"]
    assert result.usage.commands == 1

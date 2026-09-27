from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import Field

from deerflow.compile.agent_workflow_runtime_v3 import run_agent_workflow_node_v3
from deerflow.compile.agent_workflow_schemas import (
    AgentBuildNodeInput,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
    SubmitCandidateRequest,
)
from deerflow.compile.candidate_verifier import (
    CandidateVerificationCode,
    CandidateVerifier,
    FunctionalCheckEvidence,
)
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


class RecordingFunctionalRunner:
    def __init__(self, outcomes: Sequence[bool] = (True,)):
        self.outcomes = list(outcomes)
        self.calls = 0

    def run(self, *, spec: FunctionalOracleSpec, session: CompileSession, manager: Any) -> FunctionalCheckEvidence:
        del session, manager
        passed = self.outcomes[self.calls]
        self.calls += 1
        return FunctionalCheckEvidence(
            oracle_ref=spec.oracle_ref,
            passed=passed,
            command_id=f"command-oracle-{self.calls}",
            exit_code=0 if passed else 1,
            timed_out=False,
            stdout_sha256=hashlib.sha256(b"ok" if passed else b"").hexdigest(),
            stderr_sha256=hashlib.sha256(b"" if passed else b"missing header").hexdigest(),
        )


class ScriptedChatModel(BaseChatModel):
    responses: list[AIMessage]
    calls: int = 0
    bind_kwargs: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "prefreeze-scripted-zero-provider"

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
        del messages, stop, run_manager, kwargs
        response = self.responses[self.calls]
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=response)])


def _budget() -> AgentWorkflowBudget:
    return AgentWorkflowBudget(
        max_model_requests=8,
        max_recorded_tokens=None,
        max_agent_steps=24,
        max_tool_calls=16,
        max_commands=8,
        node_timeout_seconds=600,
        command_timeout_seconds=300,
        evaluator_timeout_seconds=600,
        replay_timeout_seconds=1_200,
        cleanup_timeout_seconds=120,
    )


def _make_session(tmp_path: Path) -> CompileSession:
    session_dir = tmp_path / "thread-001" / "session-001"
    artifacts_dir = session_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)
    now = utc_now_iso()
    return CompileSession(
        session_id="session-001",
        thread_id="thread-001",
        run_id="run-001",
        repo_url="https://example.invalid/repo.git",
        branch="main",
        commit_sha=COMMIT_SHA,
        image="autocompiler:test",
        image_id=f"sha256:{'e' * 64}",
        status="inspected",
        selected_build_system="cmake",
        leadagent_repo_dir=str(session_dir / "workspace" / "repo"),
        leadagent_artifacts_dir=str(artifacts_dir),
        leadagent_logs_dir=str(session_dir / "logs"),
        leadagent_repro_dir=str(session_dir / "repro"),
        metadata_path=str(session_dir / "session.json"),
        commands=[
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
                command="cp build/tool /artifacts/bin/tool",
                workdir="/workspace/repo",
                command_id="command-stage",
                role="artifact_stage",
                completed_at=now,
                exit_code=0,
            ),
        ],
    )


def _node_input(
    session: CompileSession,
    *,
    target_id: str = "sample-static-library",
    artifact_types: tuple[str, ...] = ("static_library",),
    patterns: tuple[str, ...] = ("lib/libsample.a",),
) -> AgentBuildNodeInput:
    return AgentBuildNodeInput(
        task_id="prefreeze-fixture",
        attempt_id="attempt-001",
        session_id=session.session_id,
        repository_url=session.repo_url,
        commit_sha=session.commit_sha or "",
        source_snapshot_sha256=SHA256_A,
        build_system_candidates=("cmake",),
        target_contract=AgentWorkflowTargetContract(
            target_id=target_id,
            artifact_types=artifact_types,
            artifact_path_patterns=patterns,
            functional_oracle_ref="oracle-prefreeze-v1",
        ),
        operation_policy_ref="prefreeze-zero-provider-v1",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=session.image_id or "",
            parallel_jobs=session.parallel_jobs,
            network_policy="compile-network-v1",
        ),
        budget=_budget(),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256=SHA256_A,
            protocol_sha256=SHA256_B,
            runner_sha256=SHA256_C,
        ),
        initial_observation={
            "required_candidate_artifacts": ("lib/libsample.a", "include/sample/api.h"),
            "zero_provider": True,
        },
    )


def _request(
    *,
    artifact_paths: tuple[str, ...] = ("include/sample/api.h", "lib/libsample.a"),
    target_mapping: dict[str, str] | None = None,
) -> SubmitCandidateRequest:
    return SubmitCandidateRequest(
        candidate_id="candidate-001",
        build_system="cmake",
        supporting_command_ids=("command-build",),
        artifact_paths=artifact_paths,
        target_mapping=target_mapping or {"sample-static-library": "lib/libsample.a"},
        recipe_command_ids=("command-build", "command-stage"),
    )


def _write(artifacts_dir: Path, relative_path: str, content: bytes = b"fixture") -> None:
    path = artifacts_dir / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _fixture_classifier(path: Path) -> str:
    if path.suffix in {".a", ".so", ".o"}:
        return {".a": "static_library", ".so": "shared_library", ".o": "object"}[path.suffix]
    if path.parent.name == "bin":
        return "executable"
    return "support_file"


def _verifier(runner: RecordingFunctionalRunner | None = None) -> CandidateVerifier:
    return CandidateVerifier(
        oracle_spec=FunctionalOracleSpec(oracle_ref="oracle-prefreeze-v1", argv=("/bin/true",)),
        functional_runner=runner or RecordingFunctionalRunner(),
        classifier=_fixture_classifier,
    )


def _finding_map(result: Any) -> dict[str, Any]:
    return {finding.code: finding for finding in result.findings}


def test_theora_shape_rejects_undeclared_libraries_and_zero_byte_file(tmp_path: Path) -> None:
    session = _make_session(tmp_path)
    artifacts = Path(session.leadagent_artifacts_dir)
    for relative_path in ("include/sample/api.h", "lib/libsample.a", "lib/libsample-dec.a", "lib/libsample-enc.a"):
        _write(artifacts, relative_path)
    _write(artifacts, "share/doc/doxygen-build.stamp", b"")

    result = _verifier().verify(request=_request(), node_input=_node_input(session), session=session, manager=FakeManager(session))  # type: ignore[arg-type]

    findings = _finding_map(result)
    assert findings[CandidateVerificationCode.UNDECLARED_COMPILED_ARTIFACT].paths == ("lib/libsample-dec.a", "lib/libsample-enc.a")
    assert findings[CandidateVerificationCode.DELIVERY_ZERO_BYTE].paths == ("share/doc/doxygen-build.stamp",)


def test_json_c_shape_rejects_extra_target_then_incomplete_header_closure(tmp_path: Path) -> None:
    session = _make_session(tmp_path)
    artifacts = Path(session.leadagent_artifacts_dir)
    _write(artifacts, "include/sample/api.h", b'#include "detail.h"\n')
    _write(artifacts, "lib/libsample.a")
    runner = RecordingFunctionalRunner(outcomes=(False,))
    verifier = _verifier(runner)

    wrong_mapping = verifier.verify(
        request=_request(target_mapping={"sample-public-headers": "include/sample/api.h", "sample-static-library": "lib/libsample.a"}),
        node_input=_node_input(session),
        session=session,
        manager=FakeManager(session),  # type: ignore[arg-type]
    )
    corrected_mapping = verifier.verify(
        request=_request(),
        node_input=_node_input(session),
        session=session,
        manager=FakeManager(session),  # type: ignore[arg-type]
    )

    assert tuple(finding.code for finding in wrong_mapping.findings) == (CandidateVerificationCode.TARGET_MAPPING_INVALID,)
    assert runner.calls == 1
    assert tuple(finding.code for finding in corrected_mapping.findings) == (CandidateVerificationCode.FUNCTIONAL_ORACLE_FAILED,)
    assert corrected_mapping.findings[0].oracle is not None
    assert corrected_mapping.findings[0].oracle.stderr_sha256 == hashlib.sha256(b"missing header").hexdigest()


@pytest.mark.parametrize(
    ("extra_paths", "expected_paths"),
    [
        (
            ("lib/libturbo-extra.a", "bin/cjpeg", "bin/djpeg", "bin/jpegtran", "bin/rdjpgcom", "bin/tjbench", "bin/wrjpgcom"),
            ("bin/cjpeg", "bin/djpeg", "bin/jpegtran", "bin/rdjpgcom", "bin/tjbench", "bin/wrjpgcom", "lib/libturbo-extra.a"),
        ),
        (("lib/libsample-test.a",), ("lib/libsample-test.a",)),
    ],
    ids=("libjpeg-broad-install", "oatpp-test-library"),
)
def test_broad_delivery_shapes_reject_all_undeclared_compiled_artifacts(
    tmp_path: Path,
    extra_paths: tuple[str, ...],
    expected_paths: tuple[str, ...],
) -> None:
    session = _make_session(tmp_path)
    artifacts = Path(session.leadagent_artifacts_dir)
    for relative_path in ("include/sample/api.h", "lib/libsample.a", *extra_paths):
        _write(artifacts, relative_path)

    result = _verifier().verify(request=_request(), node_input=_node_input(session), session=session, manager=FakeManager(session))  # type: ignore[arg-type]

    findings = _finding_map(result)
    assert findings[CandidateVerificationCode.UNDECLARED_COMPILED_ARTIFACT].paths == expected_paths


def test_rejection_path_evidence_is_bounded_and_symlinks_are_invalid(tmp_path: Path) -> None:
    session = _make_session(tmp_path)
    artifacts = Path(session.leadagent_artifacts_dir)
    _write(artifacts, "include/sample/api.h")
    _write(artifacts, "lib/libsample.a")
    for index in range(15):
        _write(artifacts, f"lib/libextra-{index:02d}.a")
    artifacts.joinpath("include/sample/escaped.h").symlink_to("/etc/passwd")

    result = _verifier().verify(request=_request(), node_input=_node_input(session), session=session, manager=FakeManager(session))  # type: ignore[arg-type]

    findings = _finding_map(result)
    undeclared = findings[CandidateVerificationCode.UNDECLARED_COMPILED_ARTIFACT]
    assert len(undeclared.paths) == 12
    assert undeclared.total_count == 15
    assert undeclared.as_payload()["truncated"] is True
    assert findings[CandidateVerificationCode.DELIVERY_INVALID].paths == ("include/sample/escaped.h",)


def _tool_call(target_mapping: dict[str, str], call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "submit_candidate_v1",
                "args": {
                    "candidate_id": "candidate-runtime-v3",
                    "build_system": "cmake",
                    "supporting_command_ids": ["command-build"],
                    "artifact_paths": ["bin/tool"],
                    "target_mapping": target_mapping,
                    "recipe_command_ids": ["command-build", "command-stage"],
                    "agent_summary": "零 Provider runtime v3 fixture",
                    "known_limitations": [],
                },
                "id": call_id,
                "type": "tool_call",
            }
        ],
        usage_metadata={"input_tokens": 7, "output_tokens": 5, "total_tokens": 12},
    )


def test_runtime_v3_returns_structured_rejection_and_freezes_only_after_repair(tmp_path: Path) -> None:
    session = _make_session(tmp_path)
    session.commands[-1].command = "cp build/tool /artifacts/bin/tool"
    artifact = Path(session.leadagent_artifacts_dir, "bin", "tool")
    artifact.parent.mkdir(parents=True)
    shutil.copy2("/bin/true", artifact)
    node_input = _node_input(
        session,
        target_id="tool-executable",
        artifact_types=("executable",),
        patterns=("bin/tool",),
    )
    node_input = replace(
        node_input,
        initial_observation={"required_candidate_artifacts": ("bin/tool",), "zero_provider": True},
    )
    model = ScriptedChatModel(
        responses=[
            _tool_call({"wrong-target": "bin/tool"}, "submit-wrong-target"),
            _tool_call({"tool-executable": "bin/tool"}, "submit-oracle-fails"),
            _tool_call({"tool-executable": "bin/tool"}, "submit-accepted"),
        ]
    )
    functional_runner = RecordingFunctionalRunner(outcomes=(False, True))

    result = asyncio.run(
        run_agent_workflow_node_v3(
            node_input=node_input,
            session=session,
            manager=FakeManager(session),  # type: ignore[arg-type]
            model=model,
            oracle_registry={"oracle-prefreeze-v1": FunctionalOracleSpec(oracle_ref="oracle-prefreeze-v1", argv=("/bin/true",))},
            functional_runner=functional_runner,
        )
    )

    assert result.node_status == "submitted"
    assert result.candidate_submitted is True
    assert result.usage.recorded_tokens == 36
    assert result.budget_terminal_reason is None
    assert model.calls == 3
    candidate_path = Path(session.metadata_path).parent / "agent-workflow" / "attempt-001" / "candidate.json"
    assert candidate_path.exists()
    events_path = candidate_path.parent / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    verifier_events = [event["payload"] for event in events if event["event_type"] == "candidate.prefreeze_verification_completed"]
    assert [event["passed"] for event in verifier_events] == [False, False, True]
    rejections = [event["payload"] for event in events if event["event_type"] == "candidate.submit_rejected"]
    assert rejections[0]["rejection_details"][0]["code"] == "target_mapping_invalid"
    assert rejections[1]["rejection_details"][0]["code"] == "functional_oracle_failed"
    assert rejections[1]["rejection_details"][0]["oracle"]["stderr_sha256"] == hashlib.sha256(b"missing header").hexdigest()

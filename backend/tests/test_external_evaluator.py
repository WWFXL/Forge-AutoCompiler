from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from deerflow.compile.agent_workflow_schemas import (
    AgentBuildNodeInput,
    AgentBuildNodeResult,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
    AgentWorkflowUsage,
    SubmitCandidateRequest,
)
from deerflow.compile.external_evaluator import (
    EXTERNAL_EVALUATOR_LAYERS,
    EXTERNAL_EVALUATOR_RULES_SHA256,
    EXTERNAL_EVALUATOR_VERSION,
    BoundCommandFunctionalOracleRunner,
    ExternalEvaluationResult,
    ExternalEvaluatorBackendResult,
    ExternalEvaluatorContractError,
    ExternalEvaluatorIdentityError,
    ExternalEvaluatorLayerResult,
    ExternalEvaluatorRunner,
    ForgeCompileEvaluationBackend,
    FunctionalOracleExecution,
    FunctionalOracleSpec,
    adjudicate_external_evaluations_v1,
)
from deerflow.compile.external_evaluator_v2 import (
    EXTERNAL_EVALUATOR_VERSION as EXTERNAL_EVALUATOR_V2_VERSION,
)
from deerflow.compile.external_evaluator_v2 import (
    ExternalEvaluatorRunner as ExternalEvaluatorRunnerV2,
)
from deerflow.compile.external_evaluator_v2 import (
    ForgeCompileEvaluationBackend as ForgeCompileEvaluationBackendV2,
)
from deerflow.compile.external_evaluator_v2 import (
    FunctionalOracleExecution as FunctionalOracleExecutionV2,
)
from deerflow.compile.external_evaluator_v3 import (
    EXTERNAL_EVALUATOR_VERSION as EXTERNAL_EVALUATOR_V3_VERSION,
)
from deerflow.compile.external_evaluator_v3 import (
    ExternalEvaluatorRunner as ExternalEvaluatorRunnerV3,
)
from deerflow.compile.external_evaluator_v3 import (
    ForgeCompileEvaluationBackend as ForgeCompileEvaluationBackendV3,
)
from deerflow.compile.external_evaluator_v3 import (
    SystemOwnedFunctionalOracleRunner,
)
from deerflow.compile.external_evaluator_v4 import (
    EXTERNAL_EVALUATOR_VERSION as EXTERNAL_EVALUATOR_V4_VERSION,
)
from deerflow.compile.external_evaluator_v4 import (
    ExternalEvaluatorRunner as ExternalEvaluatorRunnerV4,
)
from deerflow.compile.external_evaluator_v4 import (
    ForgeCompileEvaluationBackend as ForgeCompileEvaluationBackendV4,
)
from deerflow.compile.operations import SuccessfulCommandVerification
from deerflow.compile.schemas import (
    BuildArtifact,
    BuildCommandRecord,
    CommandResult,
    CompileSession,
    ReplayArtifactComparison,
    ReplayRecipe,
    ReplayRecipeStep,
    ReplayVerificationResult,
    VerificationCheck,
    utc_now_iso,
)

SHA256_A = "a" * 64
SHA256_B = "b" * 64
SHA256_C = "c" * 64
SHA256_D = "d" * 64
COMMIT_SHA = "e" * 40


class FakeManager:
    def __init__(self, session: CompileSession):
        self.session = session

    def load_session(self, session_id: str, thread_id: str | None = None) -> CompileSession:
        assert session_id == self.session.session_id
        assert thread_id == self.session.thread_id
        return self.session


class FailingManager(FakeManager):
    def load_session(self, session_id: str, thread_id: str | None = None) -> CompileSession:
        del session_id, thread_id
        raise RuntimeError("session store unavailable")


class FakeBackend:
    def __init__(self, *, failed_layer: str | None = None, raises: bool = False, bitwise: bool | None = True):
        self.failed_layer = failed_layer
        self.raises = raises
        self.bitwise = bitwise
        self.calls = 0

    def evaluate(self, **kwargs: Any) -> ExternalEvaluatorBackendResult:
        del kwargs
        self.calls += 1
        if self.raises:
            raise RuntimeError("backend failure")
        layers = tuple(
            ExternalEvaluatorLayerResult(
                layer=layer,
                status="failed" if layer == self.failed_layer else "passed",
                reason_codes=(f"{layer.lower()}_failed" if layer == self.failed_layer else f"{layer.lower()}_passed",),
            )
            for layer in EXTERNAL_EVALUATOR_LAYERS[2:]
        )
        return ExternalEvaluatorBackendResult(layers=layers, bitwise_reproducible=self.bitwise)


class FakeOracleRunner:
    def __init__(self, layer: ExternalEvaluatorLayerResult):
        self.layer = layer
        self.spec: FunctionalOracleSpec | None = None

    def run(self, *, spec: FunctionalOracleSpec, **kwargs: Any) -> FunctionalOracleExecution:
        del kwargs
        self.spec = spec
        return FunctionalOracleExecution(layer=self.layer, verification_command_ids=("command-smoke",) if self.layer.status == "passed" else ())


def make_budget() -> AgentWorkflowBudget:
    return AgentWorkflowBudget(
        max_model_requests=8,
        max_recorded_tokens=120_000,
        max_agent_steps=24,
        max_tool_calls=32,
        max_commands=24,
        node_timeout_seconds=600,
        command_timeout_seconds=300,
        evaluator_timeout_seconds=600,
        replay_timeout_seconds=1_200,
        cleanup_timeout_seconds=120,
    )


def make_session(tmp_path: Path, *, task_id: str = "task-fmt") -> CompileSession:
    session_dir = tmp_path / task_id / "session-001"
    artifacts_dir = session_dir / "artifacts"
    artifacts_dir.joinpath("lib").mkdir(parents=True)
    artifacts_dir.joinpath("lib", "libfmt.a").write_bytes(b"archive")
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
        metadata_path=str(session_dir / "session.json"),
        leadagent_repo_dir=str(session_dir / "workspace" / "repo"),
        leadagent_artifacts_dir=str(artifacts_dir),
        leadagent_logs_dir=str(session_dir / "logs"),
        leadagent_repro_dir=str(session_dir / "repro"),
        commands=commands,
    )


def make_node_input(session: CompileSession, *, task_id: str = "task-fmt", attempt_id: str = "attempt-001") -> AgentBuildNodeInput:
    return AgentBuildNodeInput(
        task_id=task_id,
        attempt_id=attempt_id,
        session_id=session.session_id,
        repository_url=session.repo_url,
        commit_sha=session.commit_sha or COMMIT_SHA,
        source_snapshot_sha256=SHA256_A,
        build_system_candidates=("cmake",),
        target_contract=AgentWorkflowTargetContract(
            target_id="fmt-library",
            artifact_types=("static_library",),
            artifact_path_patterns=("lib/libfmt.a",),
            functional_oracle_ref="oracle-fmt-link-v1",
        ),
        operation_policy_ref="compile-policy-v1",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=session.image_id or f"sha256:{SHA256_B}",
            parallel_jobs=session.parallel_jobs,
            network_policy="compile-network-v1",
        ),
        budget=make_budget(),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256=SHA256_A,
            protocol_sha256=SHA256_B,
            runner_sha256=SHA256_C,
        ),
        initial_observation={"build_system": "cmake"},
    )


def make_candidate(*, summary: str = "候选已生成。") -> SubmitCandidateRequest:
    return SubmitCandidateRequest(
        candidate_id="candidate-001",
        build_system="cmake",
        supporting_command_ids=("command-build",),
        artifact_paths=("lib/libfmt.a",),
        target_mapping={"fmt-library": "lib/libfmt.a"},
        recipe_command_ids=("command-configure", "command-build", "command-stage"),
        agent_summary=summary,
    )


def make_node_result(session: CompileSession, candidate: SubmitCandidateRequest) -> AgentBuildNodeResult:
    return AgentBuildNodeResult(
        node_status="submitted",
        candidate_generated_observed=True,
        candidate_submitted=True,
        submission_id=f"submission:{candidate.canonical_sha256()}",
        candidate_record_sha256=candidate.canonical_sha256(),
        usage=AgentWorkflowUsage(1, 15, 2, 1, 0),
        wall_clock_ms=100,
        evidence_head_sha256=SHA256_D,
        session_terminal_status=session.status,
    )


def prepare_runner(
    tmp_path: Path,
    *,
    backend: Any,
    candidate: SubmitCandidateRequest | None = None,
    task_id: str = "task-fmt",
    evaluation_id: str = "evaluation-001",
) -> tuple[ExternalEvaluatorRunner, CompileSession, Path]:
    session = make_session(tmp_path, task_id=task_id)
    node_input = make_node_input(session, task_id=task_id)
    frozen = candidate or make_candidate()
    candidate_path = Path(session.metadata_path).parent / "agent-workflow" / node_input.attempt_id / "candidate.json"
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_text(frozen.canonical_json(), encoding="utf-8")
    runner = ExternalEvaluatorRunner(
        node_input=node_input,
        node_result=make_node_result(session, frozen),
        session=session,
        manager=FakeManager(session),  # type: ignore[arg-type]
        candidate_path=candidate_path,
        evaluation_id=evaluation_id,
        backend=backend,
    )
    return runner, session, candidate_path


def test_external_evaluator_all_layers_pass_and_hash_chain_is_linked_to_node(tmp_path: Path) -> None:
    runner, _session, _candidate_path = prepare_runner(tmp_path, backend=FakeBackend(bitwise=False))

    result = runner.run()

    assert result.strict_reproducible_build_success is True
    assert result.bitwise_reproducible is False
    assert [layer.status for layer in result.layers] == ["passed"] * 6
    assert (runner.evaluation_dir / "result.json").is_file()
    assert (runner.evaluation_dir / "summary.json").is_file()
    events = [json.loads(line) for line in (runner.evaluation_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    previous_hash = SHA256_D
    for sequence, event in enumerate(events, start=1):
        event_hash = event.pop("event_hash")
        assert event["sequence"] == sequence
        assert event["previous_hash"] == previous_hash
        canonical = json.dumps(event, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        assert event_hash == hashlib.sha256(canonical.encode()).hexdigest()
        previous_hash = event_hash
    assert result.evidence_head_sha256 == previous_hash


def test_external_evaluator_public_api_is_lazy_importable() -> None:
    from deerflow.compile import ForgeCompileEvaluationBackend as PublicBackend
    from deerflow.compile import adjudicate_external_evaluations_v1 as public_adjudicate
    from deerflow.compile import run_external_evaluator_v1 as public_run

    assert PublicBackend is ForgeCompileEvaluationBackend
    assert public_adjudicate is adjudicate_external_evaluations_v1
    assert public_run.__module__ == "deerflow.compile.external_evaluator"


@pytest.mark.parametrize("failed_layer", ["S2", "S3", "S4", "S5"])
def test_external_evaluator_reports_each_backend_layer_failure(tmp_path: Path, failed_layer: str) -> None:
    runner, _session, _candidate_path = prepare_runner(tmp_path, backend=FakeBackend(failed_layer=failed_layer))

    result = runner.run()

    assert result.strict_reproducible_build_success is False
    assert result.primary_failure == f"{failed_layer.lower()}_failed"
    assert next(layer for layer in result.layers if layer.layer == failed_layer).status == "failed"


def test_s1_failure_blocks_backend_and_remaining_layers(tmp_path: Path) -> None:
    backend = FakeBackend()
    runner, session, _candidate_path = prepare_runner(tmp_path, backend=backend)
    session.commands[1].exit_code = 1

    result = runner.run()

    assert result.layers[1].status == "failed"
    assert "command_not_successful" in result.layers[1].reason_codes
    assert [layer.status for layer in result.layers[2:]] == ["not_run"] * 4
    assert backend.calls == 0


def test_missing_run_identity_remains_null_in_invalid_result(tmp_path: Path) -> None:
    backend = FakeBackend()
    runner, session, _candidate_path = prepare_runner(tmp_path, backend=backend)
    session.run_id = None

    result = runner.run()

    assert result.run_id is None
    assert result.layers[0].status == "invalid"
    assert "run_identity_missing" in result.layers[0].reason_codes
    assert backend.calls == 0


def test_agent_summary_cannot_change_layer_outcomes(tmp_path: Path) -> None:
    first_runner, _session, _candidate_path = prepare_runner(tmp_path / "first", backend=FakeBackend(), candidate=make_candidate(summary="成功。"), evaluation_id="evaluation-first")
    second_runner, _session, _candidate_path = prepare_runner(tmp_path / "second", backend=FakeBackend(), candidate=make_candidate(summary="失败。"), evaluation_id="evaluation-second")

    first = first_runner.run()
    second = second_runner.run()

    assert [(layer.status, layer.reason_codes) for layer in first.layers] == [(layer.status, layer.reason_codes) for layer in second.layers]
    assert first.strict_reproducible_build_success == second.strict_reproducible_build_success


def test_backend_exception_writes_failure_result_summary_and_terminal_event(tmp_path: Path) -> None:
    runner, _session, _candidate_path = prepare_runner(tmp_path, backend=FakeBackend(raises=True))

    result = runner.run()

    assert result.strict_reproducible_build_success is False
    assert result.primary_failure == "evaluator_internal_error"
    assert (runner.evaluation_dir / "failure.json").is_file()
    assert (runner.evaluation_dir / "result.json").is_file()
    assert (runner.evaluation_dir / "summary.json").is_file()
    events = [json.loads(line) for line in (runner.evaluation_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert events[-1]["event_type"] == "evaluator.terminal"
    assert events[-1]["payload"]["status"] == "failed"


def test_session_load_exception_writes_failure_result_summary_and_no_normal_checks(tmp_path: Path) -> None:
    runner, session, _candidate_path = prepare_runner(tmp_path, backend=FakeBackend())
    runner.manager = FailingManager(session)  # type: ignore[assignment]

    result = runner.run()

    assert result.layers[0].status == "invalid"
    assert result.layers[0].reason_codes == ("evaluator_internal_error",)
    assert (runner.evaluation_dir / "failure.json").is_file()
    assert (runner.evaluation_dir / "result.json").is_file()
    assert (runner.evaluation_dir / "summary.json").is_file()
    event_types = [json.loads(line)["event_type"] for line in (runner.evaluation_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert event_types == ["evaluator.started", "evaluator.failed", "evaluator.terminal"]


def test_evaluation_directory_is_create_once(tmp_path: Path) -> None:
    runner, _session, _candidate_path = prepare_runner(tmp_path, backend=FakeBackend())
    runner.run()

    with pytest.raises(ExternalEvaluatorIdentityError, match="already exists"):
        runner.run()


def test_explicit_relative_executable_preserves_uwebsockets_start_semantics() -> None:
    valid = FunctionalOracleSpec(
        oracle_ref="oracle-uwebsockets-start-v1",
        argv=("./HelloWorld",),
        requires_explicit_relative_executable=True,
    )
    invalid = replace(valid, argv=("HelloWorld",))

    assert valid.shell_command() == "./HelloWorld"
    with pytest.raises(ExternalEvaluatorContractError, match="explicit './'"):
        invalid.validate()


def test_bound_oracle_persists_stream_hashes_sizes_and_exit_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = make_session(tmp_path)
    record = BuildCommandRecord(
        stage="bash",
        command="./link-test",
        workdir="/workspace/repo",
        command_id="command-oracle",
        role="smoke",
        completed_at=utc_now_iso(),
        exit_code=7,
    )

    def fake_run_container_bash_impl(**kwargs: Any) -> tuple[CommandResult, str, BuildCommandRecord]:
        assert kwargs["command"] == "./link-test"
        session.commands.append(record)
        return CommandResult(exit_code=7, stdout="标准输出\n", stderr="error\n", combined_output="标准输出\nerror\n"), "", record

    monkeypatch.setattr("deerflow.compile.external_evaluator._run_container_bash_impl", fake_run_container_bash_impl)
    evaluation_dir = tmp_path / "evaluation"

    execution = BoundCommandFunctionalOracleRunner().run(
        spec=FunctionalOracleSpec(oracle_ref="oracle-link-v1", argv=("./link-test",), requires_explicit_relative_executable=True),
        session=session,
        manager=FakeManager(session),  # type: ignore[arg-type]
        evaluation_dir=evaluation_dir,
    )

    assert execution.layer.status == "failed"
    command, stdout, stderr = execution.layer.evidence
    assert command.exit_code == 7
    assert stdout.size_bytes == len("标准输出\n".encode())
    assert stdout.sha256 == hashlib.sha256("标准输出\n".encode()).hexdigest()
    assert stderr.size_bytes == len(b"error\n")
    assert stderr.sha256 == hashlib.sha256(b"error\n").hexdigest()
    assert (evaluation_dir / "oracle" / "stdout.log").read_text(encoding="utf-8") == "标准输出\n"
    assert (evaluation_dir / "oracle" / "stderr.log").read_text(encoding="utf-8") == "error\n"


def make_check(name: str, passed: bool = True) -> VerificationCheck:
    return VerificationCheck(name=name, target=name, command="clean_replay", passed=passed, exit_code=0 if passed else 1)


def test_forge_backend_separates_functional_replay_from_bitwise_identity(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    manager = FakeManager(session)
    candidate = make_candidate()
    node_input = make_node_input(session)
    oracle_layer = ExternalEvaluatorLayerResult(layer="S3", status="passed", reason_codes=("functional_oracle_passed",))
    oracle_runner = FakeOracleRunner(oracle_layer)
    spec = FunctionalOracleSpec(oracle_ref=node_input.target_contract.functional_oracle_ref, argv=("./link-test",), requires_explicit_relative_executable=True)
    recipe = ReplayRecipe(
        supporting_command_id="command-build",
        steps=[ReplayRecipeStep(command_id="command-build", role="build", command_sha256=SHA256_A, workdir_sha256=SHA256_B)],
        verification_steps=[ReplayRecipeStep(command_id="command-smoke", role="smoke", command_sha256=SHA256_C, workdir_sha256=SHA256_D)],
        fingerprint=SHA256_A,
    )

    def fake_submitter(**kwargs: Any) -> str:
        assert kwargs["verification_command_ids"] == ["command-smoke"]
        session.executed_build_system = "cmake"
        session.replay_recipe = recipe
        session.artifacts = [
            BuildArtifact(
                path="artifacts/lib/libfmt.a",
                source_path="/artifacts/lib/libfmt.a",
                artifact_type="static_library",
                size_bytes=7,
                sha256=SHA256_A,
            )
        ]
        session.replay_attempts = [
            ReplayVerificationResult(
                attempt_id="replay-001",
                status="failed",
                image=session.image,
                image_id=session.image_id or "",
                commit_sha=session.commit_sha or "",
                recipe_sha256=SHA256_B,
                recipe_fingerprint=recipe.fingerprint,
                cleanup_succeeded=True,
                primary_failure_classification="sha256_mismatch",
                failure_classification="sha256_mismatch",
                checks=[make_check("recipe_execution"), make_check("verification_execution"), make_check("artifact_set")],
                artifacts=[
                    ReplayArtifactComparison(
                        path="lib/libfmt.a",
                        expected_type="static_library",
                        actual_type="static_library",
                        expected_size_bytes=7,
                        actual_size_bytes=8,
                        expected_sha256=SHA256_A,
                        actual_sha256=SHA256_B,
                        type_matches=True,
                        size_matches=False,
                        sha256_matches=False,
                        smoke_matches=True,
                        passed=False,
                        mismatches=["size", "sha256"],
                    )
                ],
            )
        ]
        return json.dumps(
            {
                "candidate_status": "passed",
                "classification": None,
                "replay_attempt_id": "replay-001",
            }
        )

    backend = ForgeCompileEvaluationBackend(
        oracle_registry={spec.oracle_ref: spec},
        oracle_runner=oracle_runner,
        submitter=fake_submitter,
    )

    result = backend.evaluate(
        node_input=node_input,
        candidate=candidate,
        session=session,
        manager=manager,  # type: ignore[arg-type]
        evaluation_dir=tmp_path / "evaluation",
    )

    assert [layer.status for layer in result.layers] == ["passed"] * 4
    assert result.layers[-1].reason_codes == ("functional_replay_passed_bitwise_mismatch",)
    assert result.bitwise_reproducible is False
    assert oracle_runner.spec == spec
    assert result.layers[1].evidence[0].kind == "oracle_spec"
    assert result.layers[1].evidence[0].sha256 == spec.canonical_sha256()


def test_forge_backend_rejects_oracle_registry_identity_mismatch() -> None:
    spec = FunctionalOracleSpec(oracle_ref="oracle-a", argv=("./link-test",))

    with pytest.raises(ExternalEvaluatorContractError, match="registry key"):
        ForgeCompileEvaluationBackend(oracle_registry={"oracle-b": spec})


def test_forge_backend_binds_single_executable_target_to_successful_oracle() -> None:
    session = CompileSession(
        session_id="session-server",
        thread_id="thread-server",
        repo_url="https://example.com/server.git",
        branch=None,
        image="autocompiler:gcc13",
        status="inspected",
        commit_sha=COMMIT_SHA,
    )
    node_input = replace(
        make_node_input(session),
        target_contract=AgentWorkflowTargetContract(
            target_id="server",
            artifact_types=("executable",),
            artifact_path_patterns=("server",),
            functional_oracle_ref="oracle-server-v1",
        ),
    )
    candidate = replace(
        make_candidate(),
        artifact_paths=("server",),
        target_mapping={"server": "server"},
    )
    command = SuccessfulCommandVerification(
        command_id="command-smoke",
        command="./server",
        workdir="/artifacts",
        exit_code=0,
        output="",
        output_sha256=hashlib.sha256(b"").hexdigest(),
    )
    oracle = FunctionalOracleExecutionV2(
        layer=ExternalEvaluatorLayerResult(layer="S3", status="passed", reason_codes=("functional_oracle_passed",)),
        verification_command_ids=(command.command_id,),
        successful_commands=(command,),
    )

    policy = ForgeCompileEvaluationBackendV2._executable_verification_policy(candidate, node_input, oracle)

    assert policy is not None
    assert policy.mode == "successful_command_v1"
    assert policy.commands_by_artifact == {"server": command}


def test_s2_rejects_undeclared_artifacts_and_target_contract_drift(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    session.artifacts = [
        BuildArtifact(
            path="artifacts/lib/libfmt.a",
            source_path="/artifacts/lib/libfmt.a",
            artifact_type="static_library",
            size_bytes=7,
            sha256=SHA256_A,
        ),
        BuildArtifact(
            path="artifacts/lib/stale.a",
            source_path="/artifacts/lib/stale.a",
            artifact_type="static_library",
            size_bytes=5,
            sha256=SHA256_B,
        ),
    ]
    candidate = replace(make_candidate(), target_mapping={"wrong-target": "lib/libfmt.a"})

    layer = ForgeCompileEvaluationBackend._evaluate_s2(candidate, make_node_input(session), session, {"candidate_status": "passed"})

    assert layer.status == "failed"
    assert layer.reason_codes == ("candidate_artifact_set_mismatch", "target_mapping_invalid")


def test_s2_allows_undeclared_support_files_in_delivery_manifest(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    session.artifacts = [
        BuildArtifact(
            path="artifacts/lib/libfmt.a",
            source_path="/artifacts/lib/libfmt.a",
            artifact_type="static_library",
            size_bytes=7,
            sha256=SHA256_A,
        ),
        BuildArtifact(
            path="artifacts/include/fmt/format.h",
            source_path="/artifacts/include/fmt/format.h",
            artifact_type="support_file",
            size_bytes=5,
            sha256=SHA256_B,
        ),
    ]

    layer = ForgeCompileEvaluationBackendV2._evaluate_s2(make_candidate(), make_node_input(session), session, {"candidate_status": "passed"})

    assert layer.status == "passed"
    assert layer.reason_codes == ("candidate_artifacts_valid",)


def test_v4_s2_requires_preregistered_artifacts_in_candidate_and_delivery(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    session.artifacts = [
        BuildArtifact(
            path="artifacts/lib/libfmt.a",
            source_path="/artifacts/lib/libfmt.a",
            artifact_type="static_library",
            size_bytes=7,
            sha256=SHA256_A,
        )
    ]
    node_input = replace(
        make_node_input(session),
        initial_observation={
            "build_system": "cmake",
            "required_candidate_artifacts": ("lib/libfmt.a", "include/fmt/format.h"),
        },
    )

    layer = ForgeCompileEvaluationBackendV4._evaluate_s2(make_candidate(), node_input, session, {"candidate_status": "passed"})

    assert layer.status == "failed"
    assert layer.reason_codes == ("required_artifact_undeclared", "required_artifact_missing")


def test_v4_s2_accepts_complete_preregistered_artifact_set(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    session.artifacts = [
        BuildArtifact(
            path="artifacts/lib/libfmt.a",
            source_path="/artifacts/lib/libfmt.a",
            artifact_type="static_library",
            size_bytes=7,
            sha256=SHA256_A,
        ),
        BuildArtifact(
            path="artifacts/include/fmt/format.h",
            source_path="/artifacts/include/fmt/format.h",
            artifact_type="support_file",
            size_bytes=5,
            sha256=SHA256_B,
        ),
    ]
    candidate = replace(make_candidate(), artifact_paths=("lib/libfmt.a", "include/fmt/format.h"))
    node_input = replace(
        make_node_input(session),
        initial_observation={
            "build_system": "cmake",
            "required_candidate_artifacts": ("lib/libfmt.a", "include/fmt/format.h"),
        },
    )

    layer = ForgeCompileEvaluationBackendV4._evaluate_s2(candidate, node_input, session, {"candidate_status": "passed"})

    assert layer.status == "passed"
    assert layer.reason_codes == ("candidate_artifacts_valid",)


def test_external_evaluator_v2_records_distinct_rules_identity(tmp_path: Path) -> None:
    runner, session, candidate_path = prepare_runner(tmp_path, backend=FakeBackend(bitwise=True))
    v2_runner = ExternalEvaluatorRunnerV2(
        node_input=runner.node_input,
        node_result=runner.node_result,
        session=session,
        manager=runner.manager,
        candidate_path=candidate_path,
        evaluation_id="evaluation-v2",
        backend=runner.backend,
    )

    result = v2_runner.run()

    assert result.evaluator_version == EXTERNAL_EVALUATOR_V2_VERSION
    assert result.evaluator_version != EXTERNAL_EVALUATOR_VERSION


def test_external_evaluator_v3_records_distinct_rules_identity(tmp_path: Path) -> None:
    runner, session, candidate_path = prepare_runner(tmp_path, backend=FakeBackend(bitwise=True))
    v3_runner = ExternalEvaluatorRunnerV3(
        node_input=runner.node_input,
        node_result=runner.node_result,
        session=session,
        manager=runner.manager,
        candidate_path=candidate_path,
        evaluation_id="evaluation-v3",
        backend=runner.backend,
    )

    result = v3_runner.run()

    assert result.evaluator_version == EXTERNAL_EVALUATOR_V3_VERSION
    assert result.evaluator_version not in {EXTERNAL_EVALUATOR_VERSION, EXTERNAL_EVALUATOR_V2_VERSION}


def test_external_evaluator_v4_records_distinct_rules_identity(tmp_path: Path) -> None:
    runner, session, candidate_path = prepare_runner(tmp_path, backend=FakeBackend(bitwise=True))
    v4_runner = ExternalEvaluatorRunnerV4(
        node_input=runner.node_input,
        node_result=runner.node_result,
        session=session,
        manager=runner.manager,
        candidate_path=candidate_path,
        evaluation_id="evaluation-v4",
        backend=runner.backend,
    )

    result = v4_runner.run()

    assert result.evaluator_version == EXTERNAL_EVALUATOR_V4_VERSION
    assert result.evaluator_version not in {EXTERNAL_EVALUATOR_VERSION, EXTERNAL_EVALUATOR_V2_VERSION, EXTERNAL_EVALUATOR_V3_VERSION}


def test_v3_oracle_uses_system_owned_command_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = make_session(tmp_path)
    record = BuildCommandRecord(
        stage="bash",
        command="./link-test",
        workdir="/workspace/repo",
        command_id="command-system-oracle",
        role="smoke",
        completed_at=utc_now_iso(),
        exit_code=0,
    )
    calls: list[dict[str, Any]] = []

    def fake_system_oracle(**kwargs: Any) -> tuple[CommandResult, str, BuildCommandRecord]:
        calls.append(kwargs)
        session.commands.append(record)
        return CommandResult(exit_code=0, stdout="ok\n", stderr="", combined_output="ok\n"), "", record

    monkeypatch.setattr("deerflow.compile.external_evaluator_v3._run_system_oracle_bash_impl", fake_system_oracle)

    execution = SystemOwnedFunctionalOracleRunner().run(
        spec=FunctionalOracleSpec(oracle_ref="oracle-link-v3", argv=("./link-test",), requires_explicit_relative_executable=True),
        session=session,
        manager=FakeManager(session),  # type: ignore[arg-type]
        evaluation_dir=tmp_path / "evaluation-v3",
    )

    assert execution.layer.status == "passed"
    assert execution.verification_command_ids == ("command-system-oracle",)
    assert calls[0]["command_role"] == "smoke"


def test_v3_backend_uses_system_owned_oracle_by_default() -> None:
    spec = FunctionalOracleSpec(oracle_ref="oracle-v3", argv=("./link-test",), requires_explicit_relative_executable=True)

    backend = ForgeCompileEvaluationBackendV3(oracle_registry={spec.oracle_ref: spec})

    assert isinstance(backend.oracle_runner, SystemOwnedFunctionalOracleRunner)


def make_evaluation_result(task_id: str, *, evaluation_id: str, commit_sha: str = COMMIT_SHA, build_system: str = "cmake") -> ExternalEvaluationResult:
    layers = tuple(ExternalEvaluatorLayerResult(layer=layer, status="passed", reason_codes=(f"{layer.lower()}_passed",)) for layer in EXTERNAL_EVALUATOR_LAYERS)
    return ExternalEvaluationResult(
        evaluation_id=evaluation_id,
        task_id=task_id,
        attempt_id=f"attempt-{task_id}",
        run_id="run-001",
        session_id=f"session-{task_id}",
        submission_id=f"submission:{task_id}",
        commit_sha=commit_sha,
        build_system=build_system,
        candidate_record_sha256=SHA256_A,
        node_input_sha256=SHA256_B,
        node_result_sha256=SHA256_C,
        evaluator_version=EXTERNAL_EVALUATOR_VERSION,
        evaluator_rules_sha256=EXTERNAL_EVALUATOR_RULES_SHA256,
        layers=layers,
        strict_reproducible_build_success=True,
        bitwise_reproducible=True,
        primary_failure=None,
        started_at="2026-09-24T00:00:00+00:00",
        completed_at="2026-09-24T00:00:01+00:00",
        evidence_head_sha256=SHA256_D,
    )


def test_targeted_adjudication_replaces_only_named_task_and_preserves_order(tmp_path: Path) -> None:
    base = [make_evaluation_result("task-a", evaluation_id="evaluation-a-v1"), make_evaluation_result("task-b", evaluation_id="evaluation-b-v1")]
    replacement = replace(
        base[1],
        evaluation_id="evaluation-b-v2",
        evaluator_version="forge-external-evaluator-1.0.1",
        evaluator_rules_sha256="f" * 64,
    )

    adjudication = adjudicate_external_evaluations_v1(
        adjudication_id="adjudication-001",
        base_results=base,
        replacement_results=[replacement],
        task_order=["task-a", "task-b"],
        output_path=tmp_path / "adjudication.json",
    )

    assert [result.evaluation_id for result in adjudication.selected_evaluations] == ["evaluation-a-v1", "evaluation-b-v2"]
    assert json.loads((tmp_path / "adjudication.json").read_text(encoding="utf-8"))["task_order"] == ["task-a", "task-b"]


@pytest.mark.parametrize(
    "replacement",
    [
        make_evaluation_result("task-b", evaluation_id="evaluation-b-v2", commit_sha="f" * 40),
        make_evaluation_result("task-b", evaluation_id="evaluation-b-v2", build_system="make"),
        make_evaluation_result("task-c", evaluation_id="evaluation-c-v2"),
        replace(make_evaluation_result("task-b", evaluation_id="evaluation-b-v2"), candidate_record_sha256="f" * 64),
        replace(make_evaluation_result("task-b", evaluation_id="evaluation-b-v2"), node_input_sha256="f" * 64),
        replace(make_evaluation_result("task-b", evaluation_id="evaluation-b-v2"), node_result_sha256="f" * 64),
        replace(make_evaluation_result("task-b", evaluation_id="evaluation-b-v2"), run_id="run-002"),
        replace(make_evaluation_result("task-b", evaluation_id="evaluation-b-v2"), submission_id="submission:changed"),
    ],
)
def test_adjudication_rejects_source_identity_drift(tmp_path: Path, replacement: ExternalEvaluationResult) -> None:
    base = [make_evaluation_result("task-a", evaluation_id="evaluation-a-v1"), make_evaluation_result("task-b", evaluation_id="evaluation-b-v1")]

    with pytest.raises(ExternalEvaluatorIdentityError):
        adjudicate_external_evaluations_v1(
            adjudication_id="adjudication-001",
            base_results=base,
            replacement_results=[replacement],
            task_order=["task-a", "task-b"],
            output_path=tmp_path / "adjudication.json",
        )


def test_adjudication_output_is_create_once(tmp_path: Path) -> None:
    base = [make_evaluation_result("task-a", evaluation_id="evaluation-a-v1")]
    output = tmp_path / "adjudication.json"
    adjudicate_external_evaluations_v1(
        adjudication_id="adjudication-001",
        base_results=base,
        replacement_results=[],
        task_order=["task-a"],
        output_path=output,
    )

    with pytest.raises(ExternalEvaluatorIdentityError, match="already exists"):
        adjudicate_external_evaluations_v1(
            adjudication_id="adjudication-001",
            base_results=base,
            replacement_results=[],
            task_order=["task-a"],
            output_path=output,
        )

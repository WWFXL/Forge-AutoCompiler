"""Phase 5 v2 外部 evaluator：显式 executable oracle 与 support-file 分层。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

from deerflow.compile import external_evaluator as v1
from deerflow.compile.agent_workflow_schemas import AgentBuildNodeInput, AgentBuildNodeResult, SubmitCandidateRequest
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.operations import ExecutableVerificationPolicy, SuccessfulCommandVerification, submit_build_result_impl
from deerflow.compile.schemas import CompileSession, utc_now_iso
from deerflow.tools.bound_compile_tools import _run_container_bash_impl

EXTERNAL_EVALUATOR_SCHEMA_VERSION = v1.EXTERNAL_EVALUATOR_SCHEMA_VERSION
EXTERNAL_EVALUATOR_LAYERS = v1.EXTERNAL_EVALUATOR_LAYERS
EXTERNAL_EVALUATOR_VERSION = "forge-external-evaluator-1.1.0"
_RULES = {
    "schema_version": EXTERNAL_EVALUATOR_SCHEMA_VERSION,
    "layers": list(EXTERNAL_EVALUATOR_LAYERS),
    "strict_success": "all_layers_passed",
    "bitwise_reproducibility": "auxiliary_unless_task_contract_requires",
    "agent_report_is_truth": False,
    "targeted_reevaluation": "append_only_new_run",
    "candidate_artifacts": "declared_subset_plus_undeclared_support_files",
    "executable_verification": "single_target_successful_oracle_policy_v1",
}
EXTERNAL_EVALUATOR_RULES_SHA256 = hashlib.sha256(json.dumps(_RULES, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

ExternalEvaluationResult = v1.ExternalEvaluationResult
ExternalEvaluatorBackendResult = v1.ExternalEvaluatorBackendResult
ExternalEvaluatorContractError = v1.ExternalEvaluatorContractError
ExternalEvaluatorIdentityError = v1.ExternalEvaluatorIdentityError
ExternalEvaluatorLayerResult = v1.ExternalEvaluatorLayerResult
FunctionalOracleSpec = v1.FunctionalOracleSpec


@dataclass(frozen=True)
class FunctionalOracleExecution:
    layer: ExternalEvaluatorLayerResult
    verification_command_ids: tuple[str, ...]
    successful_commands: tuple[SuccessfulCommandVerification, ...] = ()

    def validate(self) -> None:
        self.layer.validate()
        if self.layer.layer != "S3":
            raise ExternalEvaluatorContractError("functional oracle must produce S3")
        if len(set(self.verification_command_ids)) != len(self.verification_command_ids):
            raise ExternalEvaluatorContractError("verification_command_ids must be unique")
        if self.successful_commands and tuple(command.command_id for command in self.successful_commands) != self.verification_command_ids:
            raise ExternalEvaluatorContractError("successful oracle command evidence must match verification_command_ids")
        if any(command.output_sha256 != hashlib.sha256(command.output.encode()).hexdigest() for command in self.successful_commands):
            raise ExternalEvaluatorContractError("successful oracle command output hash is invalid")


class BoundCommandFunctionalOracleRunner:
    def run(
        self,
        *,
        spec: FunctionalOracleSpec,
        session: CompileSession,
        manager: CompileSessionManager,
        evaluation_dir: Path,
    ) -> FunctionalOracleExecution:
        spec.validate()
        command_result, _message, record = _run_container_bash_impl(
            session=session,
            command=spec.shell_command(),
            timeout_seconds=spec.timeout_seconds,
            workdir=spec.workdir,
            command_role="smoke",
        )
        streams_dir = evaluation_dir / "oracle"
        stdout_path = streams_dir / "stdout.log"
        stderr_path = streams_dir / "stderr.log"
        v1._write_create_once(stdout_path, command_result.stdout)
        v1._write_create_once(stderr_path, command_result.stderr)
        stdout_bytes = command_result.stdout.encode()
        stderr_bytes = command_result.stderr.encode()
        evidence = (
            v1._reference("command", record.command_id, exit_code=record.exit_code),
            v1._reference("oracle_stdout", f"{record.command_id}:stdout", path="oracle/stdout.log", sha256=hashlib.sha256(stdout_bytes).hexdigest(), size_bytes=len(stdout_bytes)),
            v1._reference("oracle_stderr", f"{record.command_id}:stderr", path="oracle/stderr.log", sha256=hashlib.sha256(stderr_bytes).hexdigest(), size_bytes=len(stderr_bytes)),
        )
        passed = record.completed_at is not None and not record.timed_out and record.exit_code in spec.acceptable_exit_codes
        layer = v1._layer("S3", "passed" if passed else "failed", "functional_oracle_passed" if passed else "functional_oracle_failed", evidence=evidence)
        current = manager.load_session(session.session_id, session.thread_id)
        session.__dict__.update(current.__dict__)
        successful_commands = (
            (
                SuccessfulCommandVerification(
                    command_id=record.command_id,
                    command=record.command,
                    workdir=record.workdir,
                    exit_code=record.exit_code or 0,
                    output=command_result.combined_output,
                    output_sha256=hashlib.sha256(command_result.combined_output.encode()).hexdigest(),
                ),
            )
            if passed
            else ()
        )
        return FunctionalOracleExecution(
            layer=layer,
            verification_command_ids=(record.command_id,) if passed else (),
            successful_commands=successful_commands,
        )


class ForgeCompileEvaluationBackend(v1.ForgeCompileEvaluationBackend):
    def __init__(
        self,
        *,
        oracle_registry: Mapping[str, FunctionalOracleSpec],
        oracle_runner: Any | None = None,
        submitter: Callable[..., str] = submit_build_result_impl,
    ):
        super().__init__(
            oracle_registry=oracle_registry,
            oracle_runner=oracle_runner or BoundCommandFunctionalOracleRunner(),
            submitter=submitter,
        )

    def evaluate(
        self,
        *,
        node_input: AgentBuildNodeInput,
        candidate: SubmitCandidateRequest,
        session: CompileSession,
        manager: CompileSessionManager,
        evaluation_dir: Path,
    ) -> ExternalEvaluatorBackendResult:
        spec = self.oracle_registry.get(node_input.target_contract.functional_oracle_ref)
        if spec is None:
            return ExternalEvaluatorBackendResult(
                layers=(
                    v1._layer("S2", "not_run", "functional_oracle_unavailable"),
                    v1._layer("S3", "invalid", "functional_oracle_unavailable"),
                    v1._layer("S4", "not_run", "functional_oracle_unavailable"),
                    v1._layer("S5", "not_run", "functional_oracle_unavailable"),
                ),
                bitwise_reproducible=None,
            )
        oracle = self.oracle_runner.run(spec=spec, session=session, manager=manager, evaluation_dir=evaluation_dir)
        oracle.validate()
        oracle_layer = replace(
            oracle.layer,
            evidence=(v1._reference("oracle_spec", spec.oracle_ref, sha256=spec.canonical_sha256()), *oracle.layer.evidence),
        )
        oracle_layer.validate()
        payload = json.loads(
            self.submitter(
                session=session,
                supporting_command_id=candidate.supporting_command_ids[0],
                recipe_command_ids=list(candidate.recipe_command_ids),
                verification_command_ids=list(oracle.verification_command_ids),
                executable_verification_policy=self._executable_verification_policy(candidate, node_input, oracle),
            )
        )
        current = manager.load_session(session.session_id, session.thread_id)
        session.__dict__.update(current.__dict__)
        s2 = self._evaluate_s2(candidate, node_input, current, payload)
        s4 = self._evaluate_s4(candidate, current, payload)
        s5, bitwise = self._evaluate_s5(current, payload, oracle_layer.status == "passed")
        return ExternalEvaluatorBackendResult(layers=(s2, oracle_layer, s4, s5), bitwise_reproducible=bitwise)

    @staticmethod
    def _executable_verification_policy(
        candidate: SubmitCandidateRequest,
        node_input: AgentBuildNodeInput,
        oracle: FunctionalOracleExecution,
    ) -> ExecutableVerificationPolicy | None:
        target_paths = set(candidate.target_mapping.values())
        if oracle.layer.status != "passed" or set(node_input.target_contract.artifact_types) != {"executable"} or len(target_paths) != 1 or len(oracle.successful_commands) != 1 or oracle.successful_commands[0].exit_code != 0:
            return None
        return ExecutableVerificationPolicy.successful_commands({next(iter(target_paths)): oracle.successful_commands[0]})

    @classmethod
    def _evaluate_s2(
        cls,
        candidate: SubmitCandidateRequest,
        node_input: AgentBuildNodeInput,
        session: CompileSession,
        payload: Mapping[str, Any],
    ) -> ExternalEvaluatorLayerResult:
        artifact_entries = cls._session_artifacts(session)
        artifacts_by_path = {path: artifact for path, artifact in artifact_entries}
        requested_paths = set(candidate.artifact_paths)
        target_paths = set(candidate.target_mapping.values())
        reasons: list[str] = []
        if payload.get("candidate_status") != "passed":
            reasons.append("candidate_verifier_failed")
        delivery_paths = set(artifacts_by_path)
        undeclared_compiled_paths = {path for path, artifact in artifact_entries if path not in requested_paths and artifact.artifact_type != "support_file"}
        if len(artifact_entries) != len(artifacts_by_path) or not requested_paths.issubset(delivery_paths) or undeclared_compiled_paths:
            reasons.append("candidate_artifact_set_mismatch")
        allowed_types = set(node_input.target_contract.artifact_types)
        if not artifact_entries or any(not artifact.size_bytes or not artifact.sha256 for _, artifact in artifact_entries):
            reasons.append("candidate_artifact_invalid")
        target_artifacts = [artifacts_by_path[path] for path in target_paths if path in artifacts_by_path]
        if set(candidate.target_mapping) != {node_input.target_contract.target_id} or len(target_artifacts) != len(target_paths) or any(artifact.artifact_type not in allowed_types for artifact in target_artifacts):
            reasons.append("target_mapping_invalid")
        patterns = node_input.target_contract.artifact_path_patterns
        if any(not any(PurePosixPath(path).match(pattern) for pattern in patterns) for path in target_paths):
            reasons.append("target_path_mismatch")
        evidence = tuple(v1._reference("artifact", PurePosixPath(path).name, path=path, sha256=artifact.sha256, size_bytes=artifact.size_bytes) for path, artifact in artifact_entries)
        return v1._layer("S2", "passed" if not reasons else "failed", *(reasons or ["candidate_artifacts_valid"]), evidence=evidence)


class ExternalEvaluatorRunner(v1.ExternalEvaluatorRunner):
    def run(self) -> ExternalEvaluationResult:
        v1._require_identifier(self.evaluation_id, "evaluation_id")
        self.node_input.validate()
        self.node_result.validate()
        candidate = v1.load_frozen_candidate(self.candidate_path)
        try:
            self.evaluation_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise ExternalEvaluatorIdentityError(f"evaluation already exists: {self.evaluation_id}") from exc
        started_at = self.completed_clock()
        ledger = v1.ExternalEvaluatorEvidenceLedger(
            self.evaluation_dir / "events.jsonl",
            node_input=self.node_input,
            evaluation_id=self.evaluation_id,
            run_id=self.session.run_id,
            previous_hash=self.node_result.evidence_head_sha256,
        )
        ledger.append(
            "evaluator.started",
            evaluator_version=EXTERNAL_EVALUATOR_VERSION,
            evaluator_rules_sha256=EXTERNAL_EVALUATOR_RULES_SHA256,
            candidate_record_sha256=candidate.canonical_sha256(),
        )
        current = self.session
        layers: list[ExternalEvaluatorLayerResult] = []
        bitwise_reproducible: bool | None = None
        evaluator_failed = False
        try:
            current = self.manager.load_session(self.session.session_id, self.session.thread_id)
            self.session.__dict__.update(current.__dict__)
            layers.extend(
                (
                    v1._evaluate_s0(node_input=self.node_input, node_result=self.node_result, candidate=candidate, session=current),
                    v1._evaluate_s1(candidate, current),
                )
            )
            if all(layer.status == "passed" for layer in layers):
                backend_result = self.backend.evaluate(
                    node_input=self.node_input,
                    candidate=candidate,
                    session=current,
                    manager=self.manager,
                    evaluation_dir=self.evaluation_dir,
                )
                backend_result.validate()
                layers.extend(backend_result.layers)
                bitwise_reproducible = backend_result.bitwise_reproducible
            else:
                blocking_layer = next(layer.layer.lower() for layer in layers if layer.status != "passed")
                layers.extend(v1._layer(layer, "not_run", f"blocked_by_{blocking_layer}") for layer in EXTERNAL_EVALUATOR_LAYERS[2:])
        except Exception as exc:
            evaluator_failed = True
            failure = {
                "schema_version": EXTERNAL_EVALUATOR_SCHEMA_VERSION,
                "evaluation_id": self.evaluation_id,
                "task_id": self.node_input.task_id,
                "attempt_id": self.node_input.attempt_id,
                "error_class": type(exc).__name__,
                "classification": "evaluator_internal_error",
            }
            v1._write_create_once(self.evaluation_dir / "failure.json", v1._canonical_json(failure) + "\n")
            completed_layers = {layer.layer for layer in layers}
            first_missing = next(layer_name for layer_name in EXTERNAL_EVALUATOR_LAYERS if layer_name not in completed_layers)
            for layer_name in EXTERNAL_EVALUATOR_LAYERS:
                if layer_name in completed_layers:
                    continue
                status = "invalid" if layer_name == first_missing else "not_run"
                reason = "evaluator_internal_error" if status == "invalid" else "blocked_by_evaluator_error"
                layers.append(v1._layer(layer_name, status, reason))
            ledger.append("evaluator.failed", error_class=type(exc).__name__, classification="evaluator_internal_error")

        if not evaluator_failed:
            for layer in layers:
                ledger.append("evaluator.check_completed", layer=layer.layer, status=layer.status, reason_codes=list(layer.reason_codes))
        strict_success = all(layer.status == "passed" for layer in layers)
        primary_failure = next((layer.reason_codes[0] for layer in layers if layer.status != "passed"), None)
        ledger.append(
            "evaluator.terminal",
            status="passed" if strict_success else "failed",
            primary_failure=primary_failure,
            bitwise_reproducible=bitwise_reproducible,
        )
        result = ExternalEvaluationResult(
            evaluation_id=self.evaluation_id,
            task_id=self.node_input.task_id,
            attempt_id=self.node_input.attempt_id,
            run_id=current.run_id,
            session_id=current.session_id,
            submission_id=self.node_result.submission_id,
            commit_sha=self.node_input.commit_sha,
            build_system=candidate.build_system,
            candidate_record_sha256=candidate.canonical_sha256(),
            node_input_sha256=self.node_input.canonical_sha256(),
            node_result_sha256=self.node_result.canonical_sha256(),
            evaluator_version=EXTERNAL_EVALUATOR_VERSION,
            evaluator_rules_sha256=EXTERNAL_EVALUATOR_RULES_SHA256,
            layers=tuple(layers),
            strict_reproducible_build_success=strict_success,
            bitwise_reproducible=bitwise_reproducible,
            primary_failure=primary_failure,
            started_at=started_at,
            completed_at=self.completed_clock(),
            evidence_head_sha256=ledger.head_sha256,
        )
        result.validate()
        result_json = result.canonical_json()
        v1._write_create_once(self.evaluation_dir / "result.json", result_json + "\n")
        summary = {
            "schema_version": EXTERNAL_EVALUATOR_SCHEMA_VERSION,
            "evaluation_id": self.evaluation_id,
            "status": "passed" if strict_success else "failed",
            "strict_reproducible_build_success": strict_success,
            "bitwise_reproducible": bitwise_reproducible,
            "primary_failure": primary_failure,
            "result_sha256": hashlib.sha256(result_json.encode()).hexdigest(),
        }
        v1._write_create_once(self.evaluation_dir / "summary.json", v1._canonical_json(summary) + "\n")
        return result


def run_external_evaluator_v2(
    *,
    node_input: AgentBuildNodeInput,
    node_result: AgentBuildNodeResult,
    session: CompileSession,
    manager: CompileSessionManager,
    candidate_path: Path,
    evaluation_id: str,
    backend: Any,
) -> ExternalEvaluationResult:
    return ExternalEvaluatorRunner(
        node_input=node_input,
        node_result=node_result,
        session=session,
        manager=manager,
        candidate_path=candidate_path,
        evaluation_id=evaluation_id,
        backend=backend,
        completed_clock=utc_now_iso,
    ).run()

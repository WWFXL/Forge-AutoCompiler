#!/usr/bin/env python3
"""Runtime v3 双 fault-stratum、三臂、零 Provider qualification adapter。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from deerflow.compile import agent_workflow_runtime_v3 as runtime_v3
from deerflow.compile.agent_workflow_node import (
    AgentWorkflowBudgetTracker,
    AgentWorkflowCandidateStore,
    AgentWorkflowNodeStatus,
    AgentWorkflowStateMachine,
    SubmitCandidateRejectionCode,
)
from deerflow.compile.agent_workflow_schemas import SubmitCandidateRequest
from deerflow.compile.candidate_verifier import (
    CandidateVerificationCode,
    CandidateVerifier,
)

SCHEMA_VERSION = "forge-runtime-v3-three-arm-qualification-1.0.0"
FEEDBACK_SCHEMA_VERSION = "forge-contract-feedback-projection-1.0.0"
ARMS = ("c0", "t1", "t2")
STRATA = ("delivery_target", "provenance")
REPAIR_GOALS = {
    "delivery_target": "Restore consistency between the submitted candidate and the frozen delivery and target contract.",
    "provenance": "Restore a trusted build provenance chain bound to the frozen build directory, target, and artifact.",
}
TOOL_POLICY = {
    "tools": ["run_container_bash", "submit_candidate_v1"],
    "parallel_tool_calls": False,
    "action_policy": "runtime-v3-compiler-tool-surface",
}

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPONENT_PATHS = {
    "qualification_adapter": Path(__file__).resolve(),
    "qualification_docker_gate": REPO_ROOT / "backend/tests/test_forge_runtime_v3_three_arm_qualification_docker.py",
    "runtime_v3": REPO_ROOT / "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v3.py",
    "candidate_verifier": REPO_ROOT / "backend/packages/harness/deerflow/compile/candidate_verifier.py",
    "p2_reference": REPO_ROOT / "scripts/forge_opaque_build_provenance_gate.py",
    "external_evaluator_v3": REPO_ROOT / "backend/packages/harness/deerflow/compile/external_evaluator_v3.py",
    "compile_operations": REPO_ROOT / "backend/packages/harness/deerflow/compile/operations.py",
    "compiler_tool_surface": REPO_ROOT / "backend/packages/harness/deerflow/tools/bound_compile_tools.py",
}

_BASE_PAYLOAD_FIELDS = frozenset({"schema_version", "accepted", "reason"})
_FINDING_FIELDS = frozenset({"code", "paths", "expected", "actual"})
_FORBIDDEN_FEEDBACK_TERMS = (
    "argv",
    "shell",
    "command_line",
    "cmake --build",
    "make -",
    "patch",
    "diff --git",
    "standard answer",
    "correct candidate",
    "api_key",
    "credential",
    "strict_success",
    "evaluator",
    "hidden test",
)


class QualificationError(RuntimeError):
    """Qualification identity、同源性或终点门禁无效。"""


class QualificationRejectionCode(StrEnum):
    BUILD_SYSTEM_UNPROVEN = "build_system_unproven"


@dataclass(frozen=True)
class ProjectionEnvelope:
    pair_id: str
    stratum: str
    arm: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class StrictOutcome:
    candidate: bool
    functional_oracle: bool
    provenance: bool
    external_evaluator: bool
    clean_replay: bool
    cleanup: bool
    managed_orphans: tuple[str, ...] = ()
    evaluator_input: dict[str, Any] | None = None


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def component_hashes() -> dict[str, str]:
    return {name: sha256_file(path) for name, path in COMPONENT_PATHS.items()}


def _bounded_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 12:
        raise QualificationError(f"feedback {field} must be a bounded list")
    if any(not isinstance(item, str) or not item for item in value):
        raise QualificationError(f"feedback {field} contains an invalid value")
    if value != sorted(set(value)):
        raise QualificationError(f"feedback {field} must be sorted and unique")
    return value


def normalize_finding(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise QualificationError("feedback finding must be an object")
    unknown = set(value) - {
        "code",
        "paths",
        "expected",
        "actual",
        "total_count",
        "truncated",
        "oracle",
    }
    if unknown:
        raise QualificationError(f"feedback finding contains non-whitelisted fields: {sorted(unknown)}")
    code = value.get("code")
    if not isinstance(code, str) or not code:
        raise QualificationError("feedback finding code is invalid")
    finding = {
        "code": code,
        "paths": _bounded_string_list(value.get("paths", []), "paths"),
        "expected": _bounded_string_list(value.get("expected", []), "expected"),
        "actual": _bounded_string_list(value.get("actual", []), "actual"),
    }
    if value.get("oracle") is not None:
        raise QualificationError("functional oracle execution evidence is not an allowed feedback projection")
    return finding


def build_projection_set(*, pair_id: str, stratum: str, finding: dict[str, Any]) -> dict[str, ProjectionEnvelope]:
    if not pair_id or stratum not in STRATA:
        raise QualificationError("projection identity is invalid")
    normalized = normalize_finding(finding)
    common = {
        "schema_version": FEEDBACK_SCHEMA_VERSION,
        "accepted": False,
        "reason": "verification_failed",
    }
    projections = {
        "c0": copy.deepcopy(common),
        "t1": {
            **copy.deepcopy(common),
            "feedback": {
                "classification": stratum,
                "finding": copy.deepcopy(normalized),
            },
        },
        "t2": {
            **copy.deepcopy(common),
            "feedback": {
                "classification": stratum,
                "finding": copy.deepcopy(normalized),
                "repair_goal": REPAIR_GOALS[stratum],
            },
        },
    }
    result = {
        arm: ProjectionEnvelope(
            pair_id=pair_id,
            stratum=stratum,
            arm=arm,
            payload=payload,
        )
        for arm, payload in projections.items()
    }
    validate_projection_set(result, pair_id=pair_id, stratum=stratum)
    return result


def validate_projection_set(value: dict[str, ProjectionEnvelope], *, pair_id: str, stratum: str) -> None:
    if set(value) != set(ARMS):
        raise QualificationError("projection set must contain exactly C0/T1/T2")
    for arm in ARMS:
        envelope = value[arm]
        if envelope.pair_id != pair_id or envelope.stratum != stratum or envelope.arm != arm:
            raise QualificationError("cross-pair or cross-stratum feedback detected")
        payload = envelope.payload
        expected_fields = _BASE_PAYLOAD_FIELDS | (frozenset() if arm == "c0" else frozenset({"feedback"}))
        if not isinstance(payload, dict) or set(payload) != expected_fields:
            raise QualificationError(f"{arm} feedback projection fields drifted")
        if {key: payload[key] for key in _BASE_PAYLOAD_FIELDS} != value["c0"].payload:
            raise QualificationError("feedback base payload drifted across arms")
        if arm == "c0":
            continue
        feedback = payload["feedback"]
        expected_feedback_fields = {
            "classification",
            "finding",
        } | ({"repair_goal"} if arm == "t2" else set())
        if not isinstance(feedback, dict) or set(feedback) != expected_feedback_fields:
            raise QualificationError(f"{arm} feedback fields drifted")
        if feedback["classification"] != stratum:
            raise QualificationError("feedback stratum drifted")
        if set(feedback["finding"]) != _FINDING_FIELDS:
            raise QualificationError("feedback finding projection drifted")
        if arm == "t2" and feedback["repair_goal"] != REPAIR_GOALS[stratum]:
            raise QualificationError("T2 abstract repair goal drifted")

    if value["t1"].payload["feedback"]["finding"] != value["t2"].payload["feedback"]["finding"]:
        raise QualificationError("T1/T2 finding identity drifted")
    serialized = canonical_bytes({arm: value[arm].payload for arm in ARMS}).decode("utf-8").lower()
    for forbidden in _FORBIDDEN_FEEDBACK_TERMS:
        if forbidden in serialized:
            raise QualificationError(f"feedback projection leaked forbidden content: {forbidden}")


def build_arm_states(
    *,
    common_state: dict[str, Any],
    projections: dict[str, ProjectionEnvelope],
) -> dict[str, dict[str, Any]]:
    pair_id = projections["c0"].pair_id
    stratum = projections["c0"].stratum
    validate_projection_set(projections, pair_id=pair_id, stratum=stratum)
    return {
        arm: {
            "common_state": copy.deepcopy(common_state),
            "feedback": copy.deepcopy(projections[arm].payload),
        }
        for arm in ARMS
    }


def validate_state_matched(
    arm_states: dict[str, dict[str, Any]],
    *,
    pair_id: str,
    stratum: str,
) -> str:
    if set(arm_states) != set(ARMS):
        raise QualificationError("state-matched gate requires exactly C0/T1/T2")
    common_digests = {arm: canonical_sha256(arm_states[arm].get("common_state")) for arm in ARMS}
    if len(set(common_digests.values())) != 1:
        raise QualificationError("arm common state drifted")
    common = arm_states["c0"].get("common_state")
    if not isinstance(common, dict):
        raise QualificationError("arm common state is invalid")
    required = {
        "source",
        "parent_history_sha256",
        "candidate_request_sha256",
        "rejection_event_sha256",
        "message_prefix_sha256",
        "environment",
        "budget",
        "tool_policy",
        "authorities",
    }
    if set(common) != required:
        raise QualificationError("common state fields drifted")
    if common["tool_policy"] != TOOL_POLICY:
        raise QualificationError("tool or action policy drifted")
    projections = {
        arm: ProjectionEnvelope(
            pair_id=pair_id,
            stratum=stratum,
            arm=arm,
            payload=copy.deepcopy(arm_states[arm].get("feedback")),
        )
        for arm in ARMS
    }
    validate_projection_set(projections, pair_id=pair_id, stratum=stratum)
    return next(iter(common_digests.values()))


def validate_strict_outcome(value: StrictOutcome) -> None:
    layers = (
        value.candidate,
        value.functional_oracle,
        value.provenance,
        value.external_evaluator,
        value.clean_replay,
        value.cleanup,
    )
    if not all(type(item) is bool for item in layers) or not all(layers):
        raise QualificationError("strict qualification outcome is not closed")
    if value.managed_orphans:
        raise QualificationError("cleanup left managed orphans")
    evaluator_input = value.evaluator_input or {}
    serialized = canonical_bytes(evaluator_input).decode("utf-8").lower()
    if any(label in serialized for label in ("c0", "t1", "t2", "baseline", "treatment")):
        raise QualificationError("external evaluator received an arm label")


def persist_checkpoint(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if path.exists():
        raise QualificationError("checkpoint identity already exists")
    manifest = copy.deepcopy(payload)
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(canonical_bytes(manifest) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return manifest


def validate_checkpoint(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualificationError("checkpoint cannot be read") from exc
    digest = manifest.pop("manifest_sha256", None)
    if digest != canonical_sha256(manifest):
        raise QualificationError("checkpoint manifest hash drifted")
    manifest["manifest_sha256"] = digest
    return manifest


class RuntimeV3QualificationCandidateService(runtime_v3.AgentWorkflowCandidateService):
    """在 Runtime v3 submit 边界追加 P2 reference criterion。"""

    def __init__(
        self,
        *,
        provenance_evaluator: Callable[[SubmitCandidateRequest], dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.provenance_evaluator = provenance_evaluator
        self.last_provenance_finding: dict[str, Any] | None = None

    def _run_candidate_verifier(self, request: SubmitCandidateRequest) -> list[Any]:
        result = self.verifier.verify(
            request=request,
            node_input=self.node_input,
            session=self.session,
            manager=self.manager,
        )
        self._verification_findings = result.findings
        self.ledger.append("candidate.prefreeze_verification_completed", **result.evidence_payload())
        return [CandidateVerificationCode(finding.code) for finding in result.findings]

    def _validate_against_session(self, request: SubmitCandidateRequest) -> list[Any]:
        self.last_provenance_finding = None
        codes = super()._validate_against_session(request)
        if self.provenance_evaluator is None:
            return codes

        mismatch = SubmitCandidateRejectionCode.BUILD_SYSTEM_MISMATCH
        if codes == [mismatch]:
            codes = self._run_candidate_verifier(request)
        if codes:
            return list(dict.fromkeys(codes))

        observation = self.provenance_evaluator(request)
        if not isinstance(observation, dict) or observation.get("status") not in {
            "proven",
            "unproven",
        }:
            raise QualificationError("P2 evaluator returned an invalid decision")
        self.ledger.append("candidate.provenance_verification_completed", **copy.deepcopy(observation))
        if observation["status"] == "proven":
            return []
        finding = normalize_finding(
            {
                "code": QualificationRejectionCode.BUILD_SYSTEM_UNPROVEN.value,
                "paths": observation.get("paths", []),
                "expected": observation.get("expected", []),
                "actual": observation.get("actual", []),
            }
        )
        self.last_provenance_finding = finding
        return [QualificationRejectionCode.BUILD_SYSTEM_UNPROVEN]

    def _record_rejection(self, request: SubmitCandidateRequest, response: Any) -> None:
        self.ledger.append(
            "candidate.submit_rejected",
            candidate_id=request.candidate_id,
            rejection_codes=list(response.rejection_codes),
            rejection_details=[finding.as_payload() for finding in self._verification_findings],
            provenance_finding=copy.deepcopy(self.last_provenance_finding),
        )


def create_candidate_service(
    *,
    verifier: CandidateVerifier,
    provenance_evaluator: Callable[[SubmitCandidateRequest], dict[str, Any]] | None = None,
    **kwargs: Any,
) -> RuntimeV3QualificationCandidateService:
    """按 Runtime v3 的串行绑定规则创建 qualification service。"""

    if not runtime_v3._RUNTIME_BINDING_LOCK.acquire(blocking=False):
        raise QualificationError("Runtime v3 binding is already active")
    try:
        if runtime_v3._active_verifier is not None:
            raise QualificationError("Runtime v3 verifier binding is already active")
        runtime_v3._active_verifier = verifier
        try:
            return RuntimeV3QualificationCandidateService(
                provenance_evaluator=provenance_evaluator,
                **kwargs,
            )
        finally:
            runtime_v3._active_verifier = None
    finally:
        runtime_v3._RUNTIME_BINDING_LOCK.release()


def create_store(
    budget: Any,
) -> tuple[
    AgentWorkflowStateMachine,
    AgentWorkflowBudgetTracker,
    AgentWorkflowCandidateStore,
]:
    state = AgentWorkflowStateMachine()
    state.transition(AgentWorkflowNodeStatus.READY)
    state.transition(AgentWorkflowNodeStatus.RUNNING)
    tracker = AgentWorkflowBudgetTracker(budget)
    store = AgentWorkflowCandidateStore(state, tracker)
    return state, tracker, store


def _synthetic_findings() -> dict[str, dict[str, Any]]:
    return {
        "delivery_target": {
            "code": "target_mapping_invalid",
            "paths": [],
            "expected": ["forge-fixture"],
            "actual": ["wrong-target"],
        },
        "provenance": {
            "code": "build_system_unproven",
            "paths": ["build/forge-fixture"],
            "expected": ["cmake"],
            "actual": ["opaque_wrapper"],
        },
    }


def validate_contract() -> dict[str, Any]:
    projection_digests: dict[str, dict[str, str]] = {}
    for stratum, finding in _synthetic_findings().items():
        pair_id = f"qualification-{stratum}"
        projections = build_projection_set(
            pair_id=pair_id,
            stratum=stratum,
            finding=finding,
        )
        common = {
            "source": {"repository": "fixture", "commit": "a" * 40},
            "parent_history_sha256": "b" * 64,
            "candidate_request_sha256": "c" * 64,
            "rejection_event_sha256": "d" * 64,
            "message_prefix_sha256": "e" * 64,
            "environment": {
                "image_id": "sha256:" + "f" * 64,
                "workspace_sha256": "1" * 64,
                "artifacts_sha256": "2" * 64,
            },
            "budget": {
                "model_requests": 0,
                "recorded_tokens": 0,
                "agent_steps": 0,
                "tool_calls": 1,
                "commands": 0,
            },
            "tool_policy": TOOL_POLICY,
            "authorities": component_hashes(),
        }
        states = build_arm_states(common_state=common, projections=projections)
        validate_state_matched(
            states,
            pair_id=pair_id,
            stratum=stratum,
        )
        projection_digests[stratum] = {arm: canonical_sha256(projections[arm].payload) for arm in ARMS}

    validate_strict_outcome(
        StrictOutcome(
            candidate=True,
            functional_oracle=True,
            provenance=True,
            external_evaluator=True,
            clean_replay=True,
            cleanup=True,
            evaluator_input={"task_id": "qualification-task"},
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "contract_valid",
        "arms": list(ARMS),
        "strata": list(STRATA),
        "component_sha256": component_hashes(),
        "projection_sha256": projection_digests,
        "tool_policy": TOOL_POLICY,
        "provider_calls": 0,
        "formal_attempts": 0,
        "experiment_evidence_writes": 0,
        "synthetic_model_counts": {
            "requests": 0,
            "turns": 0,
            "recorded_tokens": 0,
        },
    }


def load_p2_reference() -> Any:
    module_name = "forge_runtime_v3_qualification_p2_reference"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    path = COMPONENT_PATHS["p2_reference"]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise QualificationError("P2 reference criterion cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate",))
    return parser


def main(argv: list[str] | None = None) -> int:
    _parser().parse_args(argv)
    print(
        json.dumps(
            validate_contract(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

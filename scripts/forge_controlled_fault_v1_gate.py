#!/usr/bin/env python3
"""验证 controlled artifact-staging fault 的零 provider 门禁。"""

from __future__ import annotations

import hashlib
import json
import shlex
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = "forge-controlled-fault-v1-1.0.0"
FAULT_FAMILY = "artifact_staging_missing"
EXPECTED_CLASSIFICATION = "candidate_verification_failed"
CANARY_SCHEMA_VERSION = "forge-checkpoint-primary-canary-candidate-1.0.0"


class ControlledFaultGateError(RuntimeError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(value: str, label: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ControlledFaultGateError(f"{label} must be a safe relative path")
    return path.as_posix()


@dataclass(frozen=True)
class ControlledFaultSpec:
    case_id: str
    build_output_relative_path: str
    staged_relative_path: str
    artifact_type: str

    def validate(self) -> ControlledFaultSpec:
        if not self.case_id or not self.case_id.replace("-", "").isalnum():
            raise ControlledFaultGateError("case_id is invalid")
        _safe_relative_path(self.build_output_relative_path, "build_output_relative_path")
        _safe_relative_path(self.staged_relative_path, "staged_relative_path")
        if self.artifact_type not in {"executable", "shared_library", "static_library", "object"}:
            raise ControlledFaultGateError("artifact_type is invalid")
        return self


class ControlledFaultV1:
    """只移除 staged artifact，并将白名单事实写入现有实验 ledger。"""

    def __init__(self, spec: ControlledFaultSpec, *, classifier: Callable[[Path], str | None] | None = None) -> None:
        self.spec = spec.validate()
        self.classifier = classifier or self._default_classifier

    @staticmethod
    def _default_classifier(path: Path) -> str | None:
        from deerflow.compile.operations import _classify_compiled_artifact

        return _classify_compiled_artifact(path)

    def _paths(self, session: Any) -> tuple[Path, Path]:
        workspace_artifact = Path(session.leadagent_repo_dir) / self.spec.build_output_relative_path
        staged_artifact = Path(session.leadagent_artifacts_dir) / self.spec.staged_relative_path
        return workspace_artifact, staged_artifact

    def inject(self, *, session: Any, ledger: Any, fault_id: str) -> dict[str, Any]:
        if not isinstance(fault_id, str) or not fault_id.startswith("fault_"):
            raise ControlledFaultGateError("fault_id is invalid")
        workspace_artifact, staged_artifact = self._paths(session)
        if not workspace_artifact.is_file() or not staged_artifact.is_file():
            raise ControlledFaultGateError("fault requires matching workspace and staged artifacts")
        workspace_type = self.classifier(workspace_artifact)
        staged_type = self.classifier(staged_artifact)
        if workspace_type != self.spec.artifact_type or staged_type != self.spec.artifact_type:
            raise ControlledFaultGateError("pre-fault artifact type does not match the frozen oracle")
        workspace_sha256 = sha256_file(workspace_artifact)
        staged_sha256 = sha256_file(staged_artifact)
        if workspace_sha256 != staged_sha256:
            raise ControlledFaultGateError("workspace and staged artifacts differ before fault injection")
        artifact_root = Path(session.leadagent_artifacts_dir)
        staged_files = sorted(path.relative_to(artifact_root).as_posix() for path in artifact_root.rglob("*") if path.is_file())
        if staged_files != [self.spec.staged_relative_path]:
            raise ControlledFaultGateError("fault v1 requires exactly the frozen staged artifact")

        staged_artifact.unlink()
        remaining_files = sorted(path.relative_to(artifact_root).as_posix() for path in artifact_root.rglob("*") if path.is_file())
        if remaining_files:
            raise ControlledFaultGateError("fault v1 did not produce an empty artifacts directory")

        state = {
            "fault_family": FAULT_FAMILY,
            "case_id": self.spec.case_id,
            "artifact_type": self.spec.artifact_type,
            "build_output_relative_path": self.spec.build_output_relative_path,
            "staged_relative_path": self.spec.staged_relative_path,
            "workspace_artifact_sha256": workspace_sha256,
            "staged_artifact_sha256_before_fault": staged_sha256,
            "workspace_artifact_present": True,
            "staged_artifact_present": False,
        }
        state_sha256 = sha256_bytes(canonical_bytes(state))
        event = ledger.append(
            "controlled.fault_injected",
            {
                "fault_id": fault_id,
                "session_id": session.session_id,
                **state,
                "fault_state_sha256": state_sha256,
            },
        )
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "fault_id": fault_id,
            "session_id": session.session_id,
            "state": state,
            "fault_state_sha256": state_sha256,
            "evidence_sequence": event["sequence"],
            "evidence_event_sha256": event["event_sha256"],
        }
        manifest["manifest_sha256"] = sha256_bytes(canonical_bytes(manifest))
        return manifest

    def restore_arm(self, *, session: Any, runtime: Any) -> None:
        source = f"/workspace/repo/{self.spec.build_output_relative_path}"
        target = f"/artifacts/{self.spec.staged_relative_path}"
        command = f"mkdir -p -- {shlex.quote(str(PurePosixPath(target).parent))} && cp -- {shlex.quote(source)} {shlex.quote(target)}"
        result = runtime.exec(session, command, workdir="/workspace/repo", timeout_seconds=60)
        if result.exit_code != 0:
            raise ControlledFaultGateError("failed to restore the arm artifact staging")
        workspace_artifact, staged_artifact = self._paths(session)
        if not staged_artifact.is_file() or sha256_file(staged_artifact) != sha256_file(workspace_artifact):
            raise ControlledFaultGateError("restored arm artifact differs from the workspace output")


def validate_actionable_failure(*, ledger: Any, session: Any) -> dict[str, Any]:
    events = ledger.read()
    submits = [event for event in events if event["event"] == "submit.completed"]
    failures = [event for event in events if event["event"] == "failure.recorded"]
    if len(submits) != 1 or len(failures) != 1:
        raise ControlledFaultGateError("controlled fault must produce exactly one submit and one failure")
    submit = submits[0]
    failure = failures[0]
    payload = submit["payload"]
    if payload["status"] != "failed" or payload["candidate_status"] != "failed" or payload["replay"] is not None:
        raise ControlledFaultGateError("controlled fault did not stop at a pre-replay candidate failure")
    if failure["payload"]["classification"] != EXPECTED_CLASSIFICATION or failure["payload"]["submit_attempt_id"] != payload["submit_attempt_id"]:
        raise ControlledFaultGateError("controlled fault classification or submit identity drifted")
    if session.replay_attempts:
        raise ControlledFaultGateError("controlled fault unexpectedly created a replay attempt")
    return {
        "submit_attempt_id": payload["submit_attempt_id"],
        "failure_id": failure["payload"]["failure_id"],
        "classification": EXPECTED_CLASSIFICATION,
        "submit_sequence": submit["sequence"],
        "failure_sequence": failure["sequence"],
        "ledger_head_sha256": events[-1]["event_sha256"],
        "ledger_sequence": events[-1]["sequence"],
    }


def validate_arm_submit_result(value: str) -> dict[str, Any]:
    result = json.loads(value)
    if result.get("status") != "passed" or result.get("candidate_status") != "passed" or result.get("replay_status") != "passed":
        raise ControlledFaultGateError("restored arm did not pass candidate verification and clean replay")
    return result


def validate_canary_candidate(value: dict[str, Any]) -> dict[str, Any]:
    required = {"schema_version", "document_type", "scope", "provider", "fault", "continuation", "budget", "stopping", "protocol_artifacts"}
    if set(value) != required or value.get("schema_version") != CANARY_SCHEMA_VERSION:
        raise ControlledFaultGateError("canary candidate schema is invalid")
    scope = value["scope"]
    if scope != {
        "provider_canary_authorized": False,
        "collection_authorized": False,
        "provider_calls": 0,
        "formal_physical_attempts": 0,
        "model_tokens": 0,
    }:
        raise ControlledFaultGateError("canary candidate must remain completely unauthorized")
    provider = value["provider"]
    if provider.get("model") != "deepseek-v4-flash" or provider.get("request_timeout_seconds") != 300 or provider.get("max_retries") != 0:
        raise ControlledFaultGateError("primary provider candidate drifted")
    fault = value["fault"]
    if fault.get("family") != FAULT_FAMILY or fault.get("expected_classification") != EXPECTED_CLASSIFICATION or fault.get("replay_attempts_required") != 0:
        raise ControlledFaultGateError("controlled fault candidate drifted")
    continuation = value["continuation"]
    if continuation != {
        "checkpoint_pairs": 1,
        "arms_per_pair": 2,
        "maximum_requests_per_arm": 8,
        "maximum_model_turns_per_arm": 8,
        "maximum_graph_steps_per_arm": 24,
        "work_wall_clock_seconds_per_arm": 600,
        "cleanup_reserve_seconds_per_arm": 120,
        "maximum_recorded_tokens_per_arm": 120000,
    }:
        raise ControlledFaultGateError("continuation budget drifted")
    budget = value["budget"]
    if budget != {
        "reachability_requests": 1,
        "reachability_expected_tokens": 5000,
        "reachability_maximum_tokens": 5000,
        "mechanism_canary_expected_tokens": 120000,
        "mechanism_canary_maximum_tokens": 240000,
        "stage_expected_tokens": 125000,
        "stage_maximum_tokens": 245000,
    }:
        raise ControlledFaultGateError("canary token budget drifted")
    if (
        budget["stage_expected_tokens"] != budget["reachability_expected_tokens"] + budget["mechanism_canary_expected_tokens"]
        or budget["stage_maximum_tokens"] != budget["reachability_maximum_tokens"] + budget["mechanism_canary_maximum_tokens"]
    ):
        raise ControlledFaultGateError("canary token arithmetic drifted")
    if value["stopping"].get("canary_pass_does_not_authorize_pilot") is not True:
        raise ControlledFaultGateError("pilot authorization boundary is missing")
    artifacts = value["protocol_artifacts"]
    if not isinstance(artifacts, list) or not artifacts or any(set(item) != {"path", "sha256"} for item in artifacts):
        raise ControlledFaultGateError("protocol artifact identities are invalid")
    return value

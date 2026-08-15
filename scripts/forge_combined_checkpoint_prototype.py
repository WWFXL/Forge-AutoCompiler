#!/usr/bin/env python3
"""验证消息、环境与预算 checkpoint 原子绑定的非模型组合原型。"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import forge_budget_checkpoint_prototype as budget_checkpoint
import forge_environment_checkpoint_prototype as environment_checkpoint
import forge_failure_checkpoint_prototype as message_checkpoint

SCHEMA_VERSION = "forge-combined-checkpoint-1.0.0"
CAPTURE_POINT = "after-actionable-submit-before-continuation"
ARMS = (message_checkpoint.BASELINE_ARM, message_checkpoint.TREATMENT_ARM)
_IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9-]{0,95}")

CaptureCallback = Callable[[str, str], dict[str, Any]]


class CombinedCheckpointError(RuntimeError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def manifest_payload_sha256(manifest: dict[str, Any]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    return sha256_bytes(canonical_bytes(payload))


def _require_exact_fields(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise CombinedCheckpointError(f"{label} fields do not match the frozen schema")
    return value


def _require_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise CombinedCheckpointError(f"{label} is invalid")
    return value


def _validate_arm_plan(value: Any) -> dict[str, Any]:
    plan = _require_exact_fields(value, set(ARMS), "arm_plan")
    seen: dict[str, set[str]] = {
        "thread_id": set(),
        "session_id": set(),
        "environment_id": set(),
    }
    for arm in ARMS:
        identity = _require_exact_fields(
            plan[arm],
            {"thread_id", "session_id", "environment_id"},
            f"arm_plan.{arm}",
        )
        for field_name in seen:
            value = _require_identifier(identity[field_name], f"arm_plan.{arm}.{field_name}")
            if value in seen[field_name]:
                raise CombinedCheckpointError(f"arm_plan {field_name} values must be unique")
            seen[field_name].add(value)
    return plan


def validate_combined_manifest(value: Any) -> dict[str, Any]:
    manifest = _require_exact_fields(
        value,
        {
            "schema_version",
            "manifest_sha256",
            "capture_id",
            "capture_point",
            "neutral",
            "components",
            "arm_plan",
        },
        "combined manifest",
    )
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise CombinedCheckpointError("combined manifest schema version is invalid")
    capture_id = _require_identifier(manifest["capture_id"], "capture_id")
    if manifest["capture_point"] != CAPTURE_POINT or manifest["neutral"] is not True:
        raise CombinedCheckpointError("combined capture boundary is invalid")

    components = _require_exact_fields(
        manifest["components"],
        {"message", "environment", "budget"},
        "components",
    )
    message = _require_exact_fields(
        components["message"],
        {"fixture_id", "fixture_sha256", "canonical_state_sha256", "neutral_thread_id"},
        "components.message",
    )
    for field_name in ("fixture_id", "fixture_sha256", "canonical_state_sha256", "neutral_thread_id"):
        if not isinstance(message[field_name], str) or not message[field_name]:
            raise CombinedCheckpointError(f"components.message.{field_name} is invalid")

    environment = _require_exact_fields(
        components["environment"],
        {"run_id", "manifest_sha256", "continuation_image_id"},
        "components.environment",
    )
    budget = _require_exact_fields(
        components["budget"],
        {"checkpoint_id", "manifest_sha256"},
        "components.budget",
    )
    if environment["run_id"] != capture_id or budget["checkpoint_id"] != capture_id:
        raise CombinedCheckpointError("component capture identities do not match capture_id")
    if message["neutral_thread_id"] != f"{capture_id}-neutral":
        raise CombinedCheckpointError("neutral message thread does not match capture_id")
    for component, fields in ((environment, ("manifest_sha256", "continuation_image_id")), (budget, ("manifest_sha256",))):
        for field_name in fields:
            if not isinstance(component[field_name], str) or not component[field_name]:
                raise CombinedCheckpointError(f"component {field_name} is invalid")

    _validate_arm_plan(manifest["arm_plan"])
    if manifest["manifest_sha256"] != manifest_payload_sha256(manifest):
        raise CombinedCheckpointError("combined manifest SHA-256 does not match its payload")
    return manifest


@dataclass
class ArmEnvironment:
    identity: str
    parent_manifest_sha256: str
    rootfs_overlay: dict[str, str] = field(default_factory=dict)
    workspace_overlay: dict[str, str] = field(default_factory=dict)
    artifacts_overlay: dict[str, str] = field(default_factory=dict)

    def write(self, layer: str, path: str, content: str) -> None:
        if layer not in {"rootfs", "workspace", "artifacts"}:
            raise CombinedCheckpointError(f"unknown environment layer: {layer}")
        if not isinstance(path, str) or not path or path.startswith("/") or ".." in path.split("/"):
            raise CombinedCheckpointError("environment overlay path is invalid")
        getattr(self, f"{layer}_overlay")[path] = content

    def canonical_state(self) -> dict[str, Any]:
        return {
            "parent_manifest_sha256": self.parent_manifest_sha256,
            "rootfs_overlay": copy.deepcopy(self.rootfs_overlay),
            "workspace_overlay": copy.deepcopy(self.workspace_overlay),
            "artifacts_overlay": copy.deepcopy(self.artifacts_overlay),
        }


@dataclass
class CombinedArm:
    arm: str
    message_config: dict[str, Any]
    session_id: str
    environment: ArmEnvironment
    budget: budget_checkpoint.BudgetCheckpointRuntime
    resumed: bool = False


class CombinedCheckpointPrototype:
    def __init__(
        self,
        fixture: dict[str, Any],
        checkpointer: Any,
        *,
        environment_capture: CaptureCallback,
        budget_capture: CaptureCallback,
        counters: message_checkpoint.PrototypeCounters | None = None,
    ) -> None:
        self.counters = counters or message_checkpoint.PrototypeCounters()
        self.message_runtime = message_checkpoint.FailureCheckpointPrototype(fixture, checkpointer, self.counters)
        self.environment_capture = environment_capture
        self.budget_capture = budget_capture
        self.combined_manifest: dict[str, Any] | None = None
        self.environment_manifest: dict[str, Any] | None = None
        self.budget_manifest: dict[str, Any] | None = None
        self.source_config: dict[str, Any] | None = None
        self.arms: dict[str, CombinedArm] = {}
        self._committed_manifest_sha256: str | None = None

    @staticmethod
    def _message_state_sha256(state: dict[str, Any]) -> str:
        return sha256_bytes(canonical_bytes(message_checkpoint.serialize_checkpoint_state(state)))

    @staticmethod
    def _build_manifest(
        *,
        capture_id: str,
        fixture: dict[str, Any],
        message_state_sha256: str,
        environment_manifest: dict[str, Any],
        budget_manifest: dict[str, Any],
        arm_plan: dict[str, Any],
    ) -> dict[str, Any]:
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "manifest_sha256": "",
            "capture_id": capture_id,
            "capture_point": CAPTURE_POINT,
            "neutral": True,
            "components": {
                "message": {
                    "fixture_id": fixture["fixture_id"],
                    "fixture_sha256": fixture["fixture_sha256"],
                    "canonical_state_sha256": message_state_sha256,
                    "neutral_thread_id": f"{capture_id}-neutral",
                },
                "environment": {
                    "run_id": environment_manifest["run_id"],
                    "manifest_sha256": environment_manifest["manifest_sha256"],
                    "continuation_image_id": environment_manifest["continuation_image_id"],
                },
                "budget": {
                    "checkpoint_id": budget_manifest["checkpoint_id"],
                    "manifest_sha256": budget_manifest["manifest_sha256"],
                },
            },
            "arm_plan": copy.deepcopy(arm_plan),
        }
        manifest["manifest_sha256"] = manifest_payload_sha256(manifest)
        return validate_combined_manifest(manifest)

    def capture(self, capture_id: str, arm_plan: dict[str, Any]) -> dict[str, Any]:
        if self.combined_manifest is not None:
            raise CombinedCheckpointError("combined checkpoint was already captured")
        _require_identifier(capture_id, "capture_id")
        _validate_arm_plan(arm_plan)

        source_config = self.message_runtime.capture(f"{capture_id}-neutral")
        source = self.message_runtime.graph.get_state(source_config)
        if tuple(source.next) != (message_checkpoint.CONTINUATION_NODE,):
            raise CombinedCheckpointError("message graph is not paused at the continuation boundary")
        message_state_sha256 = self._message_state_sha256(source.values)

        environment_manifest = environment_checkpoint.validate_checkpoint_manifest(self.environment_capture(capture_id, message_state_sha256))
        budget_manifest = budget_checkpoint.validate_manifest(self.budget_capture(capture_id, message_state_sha256))
        if environment_manifest["run_id"] != capture_id or budget_manifest["checkpoint_id"] != capture_id:
            raise CombinedCheckpointError("capture callback identity drifted")
        for arm in ARMS:
            if environment_manifest["identities"].get(arm) != arm_plan[arm]["environment_id"]:
                raise CombinedCheckpointError(f"environment identity drifted for {arm}")

        manifest = self._build_manifest(
            capture_id=capture_id,
            fixture=self.message_runtime.fixture,
            message_state_sha256=message_state_sha256,
            environment_manifest=environment_manifest,
            budget_manifest=budget_manifest,
            arm_plan=arm_plan,
        )
        self.source_config = source_config
        self.environment_manifest = copy.deepcopy(environment_manifest)
        self.budget_manifest = copy.deepcopy(budget_manifest)
        self.combined_manifest = copy.deepcopy(manifest)
        self._committed_manifest_sha256 = manifest["manifest_sha256"]
        return copy.deepcopy(manifest)

    def restore_parent(
        self,
        *,
        combined_manifest: dict[str, Any],
        environment_manifest: dict[str, Any],
        budget_manifest: dict[str, Any],
    ) -> None:
        if self.combined_manifest is not None:
            raise CombinedCheckpointError("combined checkpoint was already restored")
        combined = copy.deepcopy(validate_combined_manifest(combined_manifest))
        environment = copy.deepcopy(environment_checkpoint.validate_checkpoint_manifest(environment_manifest))
        budget = copy.deepcopy(budget_checkpoint.validate_manifest(budget_manifest))
        self.combined_manifest = combined
        self.environment_manifest = environment
        self.budget_manifest = budget
        self.source_config = self.message_runtime.config(combined["components"]["message"]["neutral_thread_id"])
        self._committed_manifest_sha256 = combined["manifest_sha256"]
        self._verify_parent()

    def _verify_parent(self) -> None:
        if any(
            value is None
            for value in (
                self.combined_manifest,
                self.environment_manifest,
                self.budget_manifest,
                self.source_config,
                self._committed_manifest_sha256,
            )
        ):
            raise CombinedCheckpointError("combined checkpoint is not committed")
        assert self.combined_manifest is not None
        assert self.environment_manifest is not None
        assert self.budget_manifest is not None
        assert self.source_config is not None
        combined = validate_combined_manifest(self.combined_manifest)
        if combined["manifest_sha256"] != self._committed_manifest_sha256:
            raise CombinedCheckpointError("committed combined manifest drifted")
        environment = environment_checkpoint.validate_checkpoint_manifest(self.environment_manifest)
        budget = budget_checkpoint.validate_manifest(self.budget_manifest)
        components = combined["components"]
        if environment["manifest_sha256"] != components["environment"]["manifest_sha256"]:
            raise CombinedCheckpointError("environment component drifted")
        if budget["manifest_sha256"] != components["budget"]["manifest_sha256"]:
            raise CombinedCheckpointError("budget component drifted")
        fixture = message_checkpoint.validate_fixture(self.message_runtime.fixture)
        if fixture["fixture_sha256"] != components["message"]["fixture_sha256"]:
            raise CombinedCheckpointError("message fixture drifted")
        source = self.message_runtime.graph.get_state(self.source_config)
        if tuple(source.next) != (message_checkpoint.CONTINUATION_NODE,):
            raise CombinedCheckpointError("neutral message checkpoint cannot resume")
        if self._message_state_sha256(source.values) != components["message"]["canonical_state_sha256"]:
            raise CombinedCheckpointError("neutral message state drifted")

    def derive_arm(self, arm: str) -> CombinedArm:
        if arm not in ARMS:
            raise CombinedCheckpointError("combined checkpoint arm is invalid")
        if arm in self.arms:
            raise CombinedCheckpointError(f"combined checkpoint arm already exists: {arm}")
        self._verify_parent()
        assert self.combined_manifest is not None
        assert self.environment_manifest is not None
        assert self.budget_manifest is not None
        assert self.source_config is not None
        identity = self.combined_manifest["arm_plan"][arm]

        environment = ArmEnvironment(
            identity=identity["environment_id"],
            parent_manifest_sha256=self.environment_manifest["manifest_sha256"],
        )
        budget = budget_checkpoint.BudgetCheckpointRuntime(
            self.budget_manifest,
            arm,
            budget_checkpoint.FakeClock(),
        )
        message_config = self.message_runtime.derive_arm(
            self.source_config,
            arm=arm,
            session_id=identity["session_id"],
            thread_id=identity["thread_id"],
        )
        combined_arm = CombinedArm(
            arm=arm,
            message_config=message_config,
            session_id=identity["session_id"],
            environment=environment,
            budget=budget,
        )
        self.arms[arm] = combined_arm
        self._verify_arm(combined_arm)
        return combined_arm

    def _verify_arm(self, combined_arm: CombinedArm) -> None:
        self._verify_parent()
        assert self.combined_manifest is not None
        identity = self.combined_manifest["arm_plan"][combined_arm.arm]
        state = self.message_runtime.graph.get_state(combined_arm.message_config)
        if state.values.get("arm") != combined_arm.arm or state.values.get("session_id") != identity["session_id"]:
            raise CombinedCheckpointError("message arm identity drifted")
        if combined_arm.message_config["configurable"]["thread_id"] != identity["thread_id"]:
            raise CombinedCheckpointError("message thread identity drifted")
        if combined_arm.environment.identity != identity["environment_id"]:
            raise CombinedCheckpointError("environment arm identity drifted")
        if combined_arm.budget.arm != combined_arm.arm:
            raise CombinedCheckpointError("budget arm identity drifted")
        if combined_arm.budget.manifest["manifest_sha256"] != self.combined_manifest["components"]["budget"]["manifest_sha256"]:
            raise CombinedCheckpointError("arm budget parent drifted")

    def canonical_initial_state(self, arm: str) -> dict[str, Any]:
        combined_arm = self.arms[arm]
        self._verify_arm(combined_arm)
        message_state = self.message_runtime.graph.get_state(combined_arm.message_config).values
        return {
            "combined_manifest_sha256": self._committed_manifest_sha256,
            "message": message_checkpoint.canonical_state_for_pairing(message_state),
            "environment": combined_arm.environment.canonical_state(),
            "budget": budget_checkpoint.canonical_initial_budget(combined_arm.budget),
        }

    def resume_arm(self, arm: str) -> dict[str, Any]:
        combined_arm = self.arms[arm]
        if combined_arm.resumed:
            raise CombinedCheckpointError(f"combined checkpoint arm already resumed: {arm}")
        self._verify_arm(combined_arm)
        combined_arm.budget.claim("graph_recursion_steps")
        combined_arm.budget.claim("compiler_model_turns")
        result = self.message_runtime.resume(combined_arm.message_config)
        combined_arm.resumed = True
        return result

    def external_counts(self) -> dict[str, int]:
        return {
            "provider_calls": self.counters.provider_calls,
            "docker_calls": self.counters.docker_calls,
            "formal_physical_attempts": self.counters.physical_attempts,
            "model_tokens": 0,
        }

#!/usr/bin/env python3
"""验证 failure checkpoint 预算重建与双臂隔离的非模型原型。"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = "forge-budget-checkpoint-1.0.0"
BASELINE_ARM = "baseline"
TREATMENT_ARM = "treatment"
ALLOWED_ARMS = frozenset({BASELINE_ARM, TREATMENT_ARM})

DISCRETE_RESOURCES = (
    "provider_requests",
    "compiler_invocations",
    "compiler_model_turns",
    "graph_recursion_steps",
    "post_build_commands",
)
LIMIT_FIELDS = set(DISCRETE_RESOURCES) | {
    "attempt_wall_clock_seconds",
    "attempt_cleanup_reserve_seconds",
    "compiler_wall_clock_seconds",
    "compiler_post_build_reserve_seconds",
}
CONSUMED_FIELDS = set(DISCRETE_RESOURCES) | {
    "attempt_wall_clock_seconds",
    "compiler_wall_clock_seconds",
    "tokens",
}
REMAINING_FIELDS = set(DISCRETE_RESOURCES) | {
    "attempt_wall_clock_seconds",
    "compiler_wall_clock_seconds",
}
PARENT_COST_FIELDS = {"tokens", "provider_requests", "compiler_invocations"}
_IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9-]{0,95}")


class BudgetCheckpointError(ValueError):
    pass


class BudgetCheckpointExceeded(RuntimeError):
    def __init__(self, resource: str, classification: str):
        self.resource = resource
        self.classification = classification
        super().__init__(f"Budget checkpoint rejected {resource}: {classification}")


def canonical_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise BudgetCheckpointError(f"value is not canonical JSON: {exc}") from exc
    return encoded.encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def manifest_payload_sha256(manifest: dict[str, Any]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    return sha256_bytes(canonical_bytes(payload))


def _require_exact_fields(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise BudgetCheckpointError(f"{label} fields do not match the frozen schema")
    return value


def _require_non_negative_integer(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise BudgetCheckpointError(f"{label} must be a non-negative integer")
    return value


def _require_non_negative_number(value: Any, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise BudgetCheckpointError(f"{label} must be a finite non-negative number")
    return value


def _subtract(limit: int | float, consumed: int | float) -> int | float:
    result = limit - consumed
    return 0 if result == 0 else result


def _expected_remaining(limits: dict[str, Any], consumed: dict[str, Any]) -> dict[str, Any]:
    return {resource: _subtract(limits[resource], consumed[resource]) for resource in REMAINING_FIELDS}


def _expected_clock(limits: dict[str, Any], consumed: dict[str, Any]) -> dict[str, Any]:
    attempt_elapsed = consumed["attempt_wall_clock_seconds"]
    compiler_elapsed = consumed["compiler_wall_clock_seconds"]
    return {
        "clock_kind": "deterministic_monotonic_offset",
        "attempt_elapsed_before_capture_seconds": attempt_elapsed,
        "attempt_total_remaining_seconds": _subtract(limits["attempt_wall_clock_seconds"], attempt_elapsed),
        "attempt_work_remaining_seconds": max(
            0,
            limits["attempt_wall_clock_seconds"] - limits["attempt_cleanup_reserve_seconds"] - attempt_elapsed,
        ),
        "compiler_elapsed_before_capture_seconds": compiler_elapsed,
        "compiler_total_remaining_seconds": _subtract(limits["compiler_wall_clock_seconds"], compiler_elapsed),
        "compiler_exploration_remaining_seconds": max(
            0,
            limits["compiler_wall_clock_seconds"] - limits["compiler_post_build_reserve_seconds"] - compiler_elapsed,
        ),
    }


def _expected_post_build(limits: dict[str, Any], consumed: dict[str, Any], *, started: bool) -> dict[str, Any]:
    return {
        "started": started,
        "reserve_seconds": limits["compiler_post_build_reserve_seconds"],
        "commands_limit": limits["post_build_commands"],
        "commands_consumed": consumed["post_build_commands"],
        "commands_remaining": limits["post_build_commands"] - consumed["post_build_commands"],
    }


def build_manifest(
    *,
    checkpoint_id: str,
    limits: dict[str, Any],
    consumed_before_capture: dict[str, Any],
    post_build_started: bool,
) -> dict[str, Any]:
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "manifest_sha256": "",
        "checkpoint_id": checkpoint_id,
        "limits": copy.deepcopy(limits),
        "consumed_before_capture": copy.deepcopy(consumed_before_capture),
        "remaining_at_capture": _expected_remaining(limits, consumed_before_capture),
        "continuation_clock": _expected_clock(limits, consumed_before_capture),
        "post_build": _expected_post_build(limits, consumed_before_capture, started=post_build_started),
        "parent_cost": {field_name: consumed_before_capture[field_name] for field_name in sorted(PARENT_COST_FIELDS)},
        "arm_identity": {
            "parent_checkpoint_id": checkpoint_id,
            "arm": "neutral",
        },
    }
    manifest["manifest_sha256"] = manifest_payload_sha256(manifest)
    return validate_manifest(manifest)


def validate_manifest(value: Any) -> dict[str, Any]:
    manifest = _require_exact_fields(
        value,
        {
            "schema_version",
            "manifest_sha256",
            "checkpoint_id",
            "limits",
            "consumed_before_capture",
            "remaining_at_capture",
            "continuation_clock",
            "post_build",
            "parent_cost",
            "arm_identity",
        },
        "manifest",
    )
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise BudgetCheckpointError("manifest schema version is invalid")
    checkpoint_id = manifest["checkpoint_id"]
    if not isinstance(checkpoint_id, str) or _IDENTIFIER_RE.fullmatch(checkpoint_id) is None:
        raise BudgetCheckpointError("checkpoint identity is invalid")

    limits = _require_exact_fields(manifest["limits"], LIMIT_FIELDS, "limits")
    consumed = _require_exact_fields(manifest["consumed_before_capture"], CONSUMED_FIELDS, "consumed_before_capture")
    remaining = _require_exact_fields(manifest["remaining_at_capture"], REMAINING_FIELDS, "remaining_at_capture")
    for resource in DISCRETE_RESOURCES:
        limit = _require_non_negative_integer(limits[resource], f"limits.{resource}")
        used = _require_non_negative_integer(consumed[resource], f"consumed_before_capture.{resource}")
        _require_non_negative_integer(remaining[resource], f"remaining_at_capture.{resource}")
        if used > limit:
            raise BudgetCheckpointError(f"consumed_before_capture.{resource} exceeds its limit")
    if limits["provider_requests"] < 1 or limits["compiler_invocations"] < 1:
        raise BudgetCheckpointError("provider and compiler invocation limits must be positive")

    for resource in ("attempt_wall_clock_seconds", "compiler_wall_clock_seconds"):
        limit = _require_non_negative_number(limits[resource], f"limits.{resource}")
        used = _require_non_negative_number(consumed[resource], f"consumed_before_capture.{resource}")
        _require_non_negative_number(remaining[resource], f"remaining_at_capture.{resource}")
        if limit <= 0 or used > limit:
            raise BudgetCheckpointError(f"{resource} limit/consumption is invalid")
    attempt_reserve = _require_non_negative_number(limits["attempt_cleanup_reserve_seconds"], "limits.attempt_cleanup_reserve_seconds")
    compiler_reserve = _require_non_negative_number(
        limits["compiler_post_build_reserve_seconds"],
        "limits.compiler_post_build_reserve_seconds",
    )
    if attempt_reserve >= limits["attempt_wall_clock_seconds"]:
        raise BudgetCheckpointError("attempt cleanup reserve must be smaller than its wall-clock limit")
    if compiler_reserve >= limits["compiler_wall_clock_seconds"]:
        raise BudgetCheckpointError("compiler post-build reserve must be smaller than its wall-clock limit")
    _require_non_negative_integer(consumed["tokens"], "consumed_before_capture.tokens")

    if remaining != _expected_remaining(limits, consumed):
        raise BudgetCheckpointError("remaining_at_capture does not equal limits minus consumed_before_capture")

    clock = _require_exact_fields(
        manifest["continuation_clock"],
        {
            "clock_kind",
            "attempt_elapsed_before_capture_seconds",
            "attempt_total_remaining_seconds",
            "attempt_work_remaining_seconds",
            "compiler_elapsed_before_capture_seconds",
            "compiler_total_remaining_seconds",
            "compiler_exploration_remaining_seconds",
        },
        "continuation_clock",
    )
    if clock != _expected_clock(limits, consumed):
        raise BudgetCheckpointError("continuation_clock does not match the frozen limits and consumption")

    post_build = _require_exact_fields(
        manifest["post_build"],
        {"started", "reserve_seconds", "commands_limit", "commands_consumed", "commands_remaining"},
        "post_build",
    )
    if type(post_build["started"]) is not bool:
        raise BudgetCheckpointError("post_build.started must be boolean")
    if post_build != _expected_post_build(limits, consumed, started=post_build["started"]):
        raise BudgetCheckpointError("post_build does not match the frozen limits and consumption")

    parent_cost = _require_exact_fields(manifest["parent_cost"], PARENT_COST_FIELDS, "parent_cost")
    if parent_cost != {field_name: consumed[field_name] for field_name in sorted(PARENT_COST_FIELDS)}:
        raise BudgetCheckpointError("parent_cost does not preserve capture-before cost")
    identity = _require_exact_fields(manifest["arm_identity"], {"parent_checkpoint_id", "arm"}, "arm_identity")
    if identity != {"parent_checkpoint_id": checkpoint_id, "arm": "neutral"}:
        raise BudgetCheckpointError("parent manifest arm identity is invalid")

    digest = manifest_payload_sha256(manifest)
    if manifest["manifest_sha256"] != digest:
        raise BudgetCheckpointError("manifest SHA-256 does not match canonical payload")
    return manifest


@dataclass
class FakeClock:
    current: float = 0.0

    def __call__(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        _require_non_negative_number(seconds, "clock advance")
        self.current += seconds


@dataclass
class BudgetCheckpointRuntime:
    manifest: dict[str, Any]
    arm: str
    clock: Callable[[], float]
    started_monotonic: float = field(init=False)
    claims: dict[str, int] = field(init=False)
    continuation_tokens: int = 0
    lock: threading.RLock = field(default_factory=threading.RLock)

    def __post_init__(self) -> None:
        if self.arm not in ALLOWED_ARMS:
            raise BudgetCheckpointError("continuation arm is invalid")
        self.manifest = copy.deepcopy(validate_manifest(self.manifest))
        self.started_monotonic = self.clock()
        self.claims = {resource: 0 for resource in DISCRETE_RESOURCES}

    def _elapsed(self) -> float:
        elapsed = self.clock() - self.started_monotonic
        if elapsed < 0:
            raise BudgetCheckpointError("continuation clock moved backwards")
        return elapsed

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            elapsed = self._elapsed()
            initial = self.manifest["remaining_at_capture"]
            clock = self.manifest["continuation_clock"]
            return {
                "checkpoint_id": self.manifest["checkpoint_id"],
                "manifest_sha256": self.manifest["manifest_sha256"],
                "arm": self.arm,
                "continuation_elapsed_seconds": elapsed,
                "remaining": {
                    **{resource: initial[resource] - self.claims[resource] for resource in DISCRETE_RESOURCES},
                    "attempt_total_wall_clock_seconds": max(0, clock["attempt_total_remaining_seconds"] - elapsed),
                    "attempt_work_wall_clock_seconds": max(0, clock["attempt_work_remaining_seconds"] - elapsed),
                    "compiler_total_wall_clock_seconds": max(0, clock["compiler_total_remaining_seconds"] - elapsed),
                    "compiler_exploration_wall_clock_seconds": max(0, clock["compiler_exploration_remaining_seconds"] - elapsed),
                },
                "post_build_started": self.manifest["post_build"]["started"],
            }

    def claim(self, resource: str) -> dict[str, Any]:
        if resource not in DISCRETE_RESOURCES:
            raise BudgetCheckpointError(f"unknown budget resource: {resource}")
        with self.lock:
            snapshot = self.snapshot()
            remaining = snapshot["remaining"]
            if remaining["attempt_work_wall_clock_seconds"] <= 0:
                raise BudgetCheckpointExceeded(resource, "attempt_work_deadline_reached")
            if resource in {"compiler_model_turns", "graph_recursion_steps"} and remaining["compiler_exploration_wall_clock_seconds"] <= 0:
                raise BudgetCheckpointExceeded(resource, "compiler_exploration_deadline_reached")
            if resource == "post_build_commands":
                if not snapshot["post_build_started"]:
                    raise BudgetCheckpointExceeded(resource, "post_build_not_started")
                if remaining["compiler_total_wall_clock_seconds"] <= 0:
                    raise BudgetCheckpointExceeded(resource, "compiler_total_deadline_reached")
            if remaining[resource] <= 0:
                raise BudgetCheckpointExceeded(resource, f"{resource}_limit_reached")
            self.claims[resource] += 1
            return self.snapshot()

    def record_tokens(self, tokens: int) -> None:
        _require_non_negative_integer(tokens, "continuation tokens")
        with self.lock:
            self.continuation_tokens += tokens

    def allow_terminal_action(self, action: str) -> dict[str, Any]:
        if action not in {"finalize", "cleanup"}:
            raise BudgetCheckpointError("unknown terminal action")
        return self.snapshot()

    def cost_report(self) -> dict[str, Any]:
        with self.lock:
            parent = copy.deepcopy(self.manifest["parent_cost"])
            continuation = {
                "tokens": self.continuation_tokens,
                "provider_requests": self.claims["provider_requests"],
                "compiler_invocations": self.claims["compiler_invocations"],
            }
            return {
                "checkpoint_id": self.manifest["checkpoint_id"],
                "arm": self.arm,
                "parent_cost": parent,
                "continuation_cost": continuation,
                "total_cost": {field_name: parent[field_name] + continuation[field_name] for field_name in sorted(PARENT_COST_FIELDS)},
            }


def canonical_initial_budget(runtime: BudgetCheckpointRuntime) -> dict[str, Any]:
    snapshot = runtime.snapshot()
    return {
        "checkpoint_id": snapshot["checkpoint_id"],
        "manifest_sha256": snapshot["manifest_sha256"],
        "continuation_elapsed_seconds": snapshot["continuation_elapsed_seconds"],
        "remaining": snapshot["remaining"],
        "post_build_started": snapshot["post_build_started"],
    }

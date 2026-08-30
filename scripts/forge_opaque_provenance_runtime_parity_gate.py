#!/usr/bin/env python3
"""Issue #186 opaque provenance checkpoint runtime-parity 零 provider 门禁。"""

from __future__ import annotations

import argparse
import json
import posixpath
import shlex
import threading
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, override

import forge_opaque_build_provenance_real_docker_gate as opaque
from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse

SCHEMA_VERSION = "forge-opaque-provenance-runtime-parity-gate-1.0.0"
MEASUREMENT_CLASSIFICATION = "measurement_policy_censored"
INTERVENTION_CLASSIFICATION = "intervention_delivery_failure"

ACTION_LIMITS = {
    "inspection": 4,
    "repair_build": 2,
    "artifact_stage": 2,
    "submit": 2,
}

_SHELL_CONTROL_TOKENS = frozenset({"&&", "||", ";", "|", ">", ">>", "<", "<<"})
_FORBIDDEN_ROLES = frozenset({"clone", "configure", "dependency_setup", "housekeeping", "replay_delay"})


class RuntimeParityGateError(RuntimeError):
    """Runtime-parity 契约或动作预算被拒绝。"""


@dataclass(frozen=True)
class FrozenActionPolicy:
    workdir: str = opaque.WORKDIR
    build_directory: str = opaque.BUILD_DIRECTORY
    target: str = opaque.TARGET
    build_output: str = f"{opaque.WORKDIR}/{opaque.BUILD_OUTPUT}"
    staged_artifact: str = f"/artifacts/{opaque.STAGED_ARTIFACT}"


@dataclass
class AtomicActionBudget:
    limits: dict[str, int] = field(default_factory=lambda: dict(ACTION_LIMITS))
    _consumed: dict[str, int] = field(init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def __post_init__(self) -> None:
        if self.limits != ACTION_LIMITS:
            raise RuntimeParityGateError("action limits drifted from the preregistered gate")
        self._consumed = {action: 0 for action in self.limits}

    def claim(self, *actions: str) -> dict[str, Any]:
        if not actions:
            raise RuntimeParityGateError("at least one action must be claimed")
        with self._lock:
            requested = {action: actions.count(action) for action in set(actions)}
            for action, count in requested.items():
                if action not in self.limits:
                    raise RuntimeParityGateError(f"unknown action: {action}")
                if self._consumed[action] + count > self.limits[action]:
                    raise RuntimeParityGateError(f"{action} budget exhausted")
            for action, count in requested.items():
                self._consumed[action] += count
            return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "limits": dict(self.limits),
                "consumed": dict(self._consumed),
                "remaining": {action: self.limits[action] - self._consumed[action] for action in self.limits},
            }


def serial_model_settings(current: dict[str, Any] | None = None) -> dict[str, Any]:
    return {**(current or {}), "parallel_tool_calls": False}


class SerialToolCallMiddleware(AgentMiddleware[AgentState]):
    """让 create_agent 最终调用 model.bind_tools(..., parallel_tool_calls=False)。"""

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        return handler(request.override(model_settings=serial_model_settings(request.model_settings)))

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        return await handler(request.override(model_settings=serial_model_settings(request.model_settings)))


def _tokens(command: str) -> list[str]:
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise RuntimeParityGateError("command is not valid shell token input") from exc
    if not tokens or any(token in _SHELL_CONTROL_TOKENS for token in tokens):
        raise RuntimeParityGateError("compound shell commands are forbidden")
    return tokens


def _absolute_container_path(value: str, *, workdir: str) -> str:
    path = value if value.startswith("/") else posixpath.join(workdir, value)
    normalized = posixpath.normpath(path)
    if not normalized.startswith("/"):
        raise RuntimeParityGateError("container path must be absolute")
    return normalized


def validate_repair_build(
    command: str,
    *,
    workdir: str,
    policy: FrozenActionPolicy,
) -> None:
    tokens = _tokens(command)
    if len(tokens) < 5 or tokens[:2] != ["cmake", "--build"]:
        raise RuntimeParityGateError("repair build must be a direct cmake --build invocation")
    if _absolute_container_path(tokens[2], workdir=workdir) != policy.build_directory:
        raise RuntimeParityGateError("repair build directory drifted from the frozen identity")
    if tokens[3:5] != ["--target", policy.target]:
        raise RuntimeParityGateError("repair build target drifted from the frozen identity")
    remainder = tokens[5:]
    if not remainder:
        return
    if len(remainder) == 1 and remainder[0].startswith("-j") and remainder[0][2:].isdigit():
        return
    if len(remainder) in {1, 2} and remainder[0] == "--parallel" and (len(remainder) == 1 or remainder[1].isdigit()):
        return
    raise RuntimeParityGateError("repair build contains non-preregistered arguments")


def validate_artifact_stage(
    command: str,
    *,
    workdir: str,
    policy: FrozenActionPolicy,
) -> None:
    tokens = _tokens(command)
    if len(tokens) != 3 or tokens[0] != "cp":
        raise RuntimeParityGateError("artifact stage must copy exactly one frozen output")
    source = _absolute_container_path(tokens[1], workdir=workdir)
    destination = _absolute_container_path(tokens[2], workdir=workdir)
    if (source, destination) != (policy.build_output, policy.staged_artifact):
        raise RuntimeParityGateError("artifact stage identity drifted from the frozen output")


def classify_action(
    command: str,
    *,
    workdir: str,
    command_role: str,
    policy: FrozenActionPolicy,
) -> str:
    from deerflow.compile.evidence import allowed_command_role
    from deerflow.compile.operations import infer_command_roles, resolve_command_role

    declared = allowed_command_role(command_role)
    effective, _inferred = resolve_command_role(command, declared)
    roles = infer_command_roles(command) | {effective}
    if roles & _FORBIDDEN_ROLES:
        raise RuntimeParityGateError("command uses a forbidden post-checkpoint role")
    if "build" in roles:
        if "artifact_stage" in roles:
            raise RuntimeParityGateError("repair build and artifact stage must be separate actions")
        validate_repair_build(command, workdir=workdir, policy=policy)
        return "repair_build"
    if "artifact_stage" in roles:
        validate_artifact_stage(command, workdir=workdir, policy=policy)
        return "artifact_stage"
    if effective not in {"other", "smoke"}:
        raise RuntimeParityGateError("command role is outside the runtime-parity action set")
    _tokens(command)
    return "inspection"


def _invoke(tool: Any, payload: dict[str, Any]) -> Any:
    if hasattr(tool, "invoke"):
        return tool.invoke(payload)
    return tool(**payload)


@dataclass
class RuntimeParityToolAdapter:
    run_tool: Any
    submit_tool: Any
    budget: AtomicActionBudget = field(default_factory=AtomicActionBudget)
    policy: FrozenActionPolicy = field(default_factory=FrozenActionPolicy)
    staged_artifacts_present: Callable[[], bool] = field(default=lambda: False)

    def run(
        self,
        command: str,
        *,
        timeout_seconds: int = 300,
        workdir: str | None = None,
        command_role: str = "other",
    ) -> Any:
        effective_workdir = workdir or self.policy.workdir
        action = classify_action(
            command,
            workdir=effective_workdir,
            command_role=command_role,
            policy=self.policy,
        )
        automatic_submit_expected = action == "artifact_stage" or (action == "repair_build" and self.staged_artifacts_present())
        claims: Iterable[str] = (action, "submit") if automatic_submit_expected else (action,)
        self.budget.claim(*claims)
        return _invoke(
            self.run_tool,
            {
                "command": command,
                "timeout_seconds": min(300, max(1, timeout_seconds)),
                "workdir": effective_workdir,
                "command_role": command_role,
            },
        )

    def submit(self, supporting_command_id: str | None = None) -> Any:
        self.budget.claim("submit")
        return _invoke(self.submit_tool, {"supporting_command_id": supporting_command_id})


def validate_gate_contract() -> dict[str, Any]:
    policy = FrozenActionPolicy()
    validate_repair_build(opaque.TREATMENT_BUILD_COMMAND, workdir=policy.workdir, policy=policy)
    validate_artifact_stage(opaque.TREATMENT_STAGE_COMMAND, workdir=policy.workdir, policy=policy)
    return {
        "schema_version": SCHEMA_VERSION,
        "issue": 186,
        "measurement_classification": MEASUREMENT_CLASSIFICATION,
        "intervention_classification": INTERVENTION_CLASSIFICATION,
        "action_limits": dict(ACTION_LIMITS),
        "parallel_tool_calls": False,
        "parent_submit_wrapper_required": True,
        "fence_released_before_capture": True,
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
        "docker_executed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate",))
    parser.parse_args(argv)
    print(json.dumps(validate_gate_contract(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

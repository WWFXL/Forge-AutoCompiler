#!/usr/bin/env python3
"""Issue #208 R2 Make runtime-parity 零 provider 动作门禁。"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

import forge_opaque_provenance_make_lifecycle_gate as make_lifecycle
import forge_opaque_provenance_runtime_parity_gate as base

SCHEMA_VERSION = "forge-opaque-provenance-make-runtime-parity-gate-1.0.0"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/208"
ACTION_LIMITS = base.ACTION_LIMITS
AtomicActionBudget = base.AtomicActionBudget
RuntimeParityGateError = base.RuntimeParityGateError
SerialToolCallMiddleware = base.SerialToolCallMiddleware

_FORBIDDEN_ROLES = frozenset({"clone", "configure", "dependency_setup", "housekeeping", "replay_delay"})


@dataclass(frozen=True)
class FrozenActionPolicy:
    workdir: str = make_lifecycle.WORKDIR
    build_directory: str = make_lifecycle.WORKDIR
    target: str = make_lifecycle.TARGET
    build_output: str = f"{make_lifecycle.WORKDIR}/{make_lifecycle.BUILD_OUTPUT}"
    staged_artifact: str = f"/artifacts/{make_lifecycle.STAGED_ARTIFACT}"
    jobs: str = "2"


def validate_repair_build(
    command: str,
    *,
    workdir: str,
    policy: FrozenActionPolicy,
) -> None:
    tokens = base._tokens(command)
    leaf = PurePosixPath(tokens[0]).name
    if leaf not in {"make", "gmake"}:
        raise RuntimeParityGateError("repair build must be a direct make or gmake invocation")
    try:
        invocation = make_lifecycle.reference.parse_make_invocation(
            leaf,
            tuple(tokens[1:]),
            workdir=workdir,
        )
    except make_lifecycle.reference.MakeReferenceError as exc:
        raise RuntimeParityGateError("repair build contains non-preregistered arguments") from exc
    if invocation.effective_directory != policy.build_directory:
        raise RuntimeParityGateError("repair build directory drifted from the frozen identity")
    if invocation.target != policy.target:
        raise RuntimeParityGateError("repair build target drifted from the frozen identity")
    if invocation.jobs != policy.jobs:
        raise RuntimeParityGateError("repair build jobs drifted from the frozen identity")


def validate_artifact_stage(
    command: str,
    *,
    workdir: str,
    policy: FrozenActionPolicy,
) -> None:
    base.validate_artifact_stage(command, workdir=workdir, policy=policy)


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
    base._tokens(command)
    return "inspection"


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
        return base._invoke(
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
        return base._invoke(
            self.submit_tool,
            {"supporting_command_id": supporting_command_id},
        )


def validate_gate_contract() -> dict[str, Any]:
    policy = FrozenActionPolicy()
    validate_repair_build(
        make_lifecycle.TREATMENT_BUILD_COMMAND,
        workdir=policy.workdir,
        policy=policy,
    )
    validate_artifact_stage(
        make_lifecycle.TREATMENT_STAGE_COMMAND,
        workdir=policy.workdir,
        policy=policy,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "issue_url": ISSUE_URL,
        "action_limits": dict(ACTION_LIMITS),
        "build_system": "make",
        "effective_directory": policy.build_directory,
        "target": policy.target,
        "jobs": policy.jobs,
        "parallel_tool_calls": False,
        "provider_calls": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
        "docker_executed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate",))
    parser.parse_args(argv)
    print(
        json.dumps(
            validate_gate_contract(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Issue #216 R3 Make candidate 的零 provider runtime gate。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import forge_opaque_provenance_make_rejection_observability_gate as make_observability
import forge_opaque_provenance_make_runtime_parity_gate as make_parity
import forge_opaque_provenance_r3_make_candidate_protocol as protocol
import forge_opaque_provenance_r3_make_construct_alignment_gate as alignment

from deerflow.compile.evidence import EvidenceError, allowed_command_role
from deerflow.compile.operations import infer_command_roles, resolve_command_role

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
ACTION_LIMITS = make_parity.ACTION_LIMITS
AtomicActionBudget = make_parity.AtomicActionBudget
CommandRunner = Callable[[Sequence[str], Path], str]
_FORBIDDEN_ROLES = frozenset({"clone", "configure", "dependency_setup", "housekeeping", "replay_delay"})


class RuntimeGateError(RuntimeError):
    """候选 runtime、只读快照或未授权入口无效。"""


class R3RuntimeParityGateError(make_parity.RuntimeParityGateError):
    def __init__(self, message: str, *, classification: str, action_kind: str) -> None:
        super().__init__(message)
        self.evidence_rejection_classification = classification
        self.evidence_action_kind = action_kind


@dataclass(frozen=True)
class R3ActionPolicy:
    workdir: str = alignment.lifecycle.WORKDIR
    build_directory: str = alignment.lifecycle.WORKDIR
    target: str = alignment.lifecycle.TARGET
    build_output: str = f"{alignment.lifecycle.WORKDIR}/{alignment.lifecycle.BUILD_OUTPUT}"
    staged_artifact: str = f"/artifacts/{alignment.lifecycle.STAGED_ARTIFACT}"
    maximum_jobs: int = 2


def validate_repair_build(command: str, *, workdir: str, policy: R3ActionPolicy) -> None:
    try:
        alignment.validate_repair_build(
            command,
            workdir=workdir,
            policy=alignment.AlignedMakePolicy(
                build_directory=policy.build_directory,
                target=policy.target,
                maximum_jobs=policy.maximum_jobs,
            ),
        )
    except alignment.ConstructAlignmentGateError as exc:
        raise R3RuntimeParityGateError(
            str(exc),
            classification=exc.evidence_rejection_classification,
            action_kind=exc.evidence_action_kind,
        ) from exc


def classify_action(command: str, *, workdir: str, command_role: str, policy: R3ActionPolicy) -> str:
    declared = allowed_command_role(command_role)
    effective, _inferred = resolve_command_role(command, declared)
    roles = infer_command_roles(command) | {effective}
    if roles & _FORBIDDEN_ROLES:
        raise make_parity.RuntimeParityGateError("command uses a forbidden post-checkpoint role")
    if "build" in roles:
        if "artifact_stage" in roles:
            raise make_parity.RuntimeParityGateError("repair build and artifact stage must be separate actions")
        validate_repair_build(command, workdir=workdir, policy=policy)
        return "repair_build"
    if "artifact_stage" in roles:
        make_parity.validate_artifact_stage(command, workdir=workdir, policy=policy)
        return "artifact_stage"
    if effective not in {"other", "smoke"}:
        raise make_parity.RuntimeParityGateError("command role is outside the runtime-parity action set")
    make_parity.base._tokens(command)
    return "inspection"


@dataclass
class RuntimeParityToolAdapter:
    run_tool: Any
    submit_tool: Any
    budget: AtomicActionBudget = field(default_factory=AtomicActionBudget)
    policy: R3ActionPolicy = field(default_factory=R3ActionPolicy)
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
        action = classify_action(command, workdir=effective_workdir, command_role=command_role, policy=self.policy)
        automatic_submit_expected = action == "artifact_stage" or (action == "repair_build" and self.staged_artifacts_present())
        claims: Iterable[str] = (action, "submit") if automatic_submit_expected else (action,)
        self.budget.claim(*claims)
        return make_parity.base._invoke(
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
        return make_parity.base._invoke(self.submit_tool, {"supporting_command_id": supporting_command_id})


class ObservableRuntimeParityToolAdapter(RuntimeParityToolAdapter):
    """将 R3 分类映射到既有 R0 companion 合同。"""

    def run(self, command: str, **kwargs: Any) -> Any:
        try:
            return super().run(command, **kwargs)
        except R3RuntimeParityGateError as exc:
            raise make_observability.ObservableRuntimeParityGateError(
                str(exc),
                classification=exc.evidence_rejection_classification,
                action_kind=exc.evidence_action_kind,
            ) from exc
        except make_parity.RuntimeParityGateError as exc:
            raise make_observability.r0._observable_gate_error(exc, action_hint=make_observability.r0._action_hint(kwargs.get("command_role", "other"))) from exc
        except EvidenceError as exc:
            if str(exc).startswith("Unsupported compile command role:"):
                raise make_observability.ObservableRuntimeParityGateError(
                    "unsupported compile command role",
                    classification="invalid_command_role",
                    action_kind="command",
                ) from exc
            raise

    def submit(self, supporting_command_id: str | None = None) -> Any:
        try:
            return super().submit(supporting_command_id)
        except make_parity.RuntimeParityGateError as exc:
            raise make_observability.r0._observable_gate_error(exc, action_hint="submit") from exc


def _run_command(command: Sequence[str], cwd: Path) -> str:
    if not command or command[0] != "git":
        raise RuntimeGateError("candidate preflight only permits read-only git commands")
    try:
        result = subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeGateError("candidate preflight git command failed") from exc
    return result.stdout.strip()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_runtime_gate_contract() -> dict[str, Any]:
    alignment.validate_gate_contract()
    policy = R3ActionPolicy()
    accepted = {command: classify_action(command, workdir=policy.workdir, command_role="build", policy=policy) for command in ("make libhoedown.a", "make -j1 libhoedown.a", "gmake --jobs=2 libhoedown.a")}
    rejected: dict[str, str] = {}
    for command in ("make -j libhoedown.a", "make -j0 libhoedown.a", "make -j3 libhoedown.a"):
        try:
            classify_action(command, workdir=policy.workdir, command_role="build", policy=policy)
        except R3RuntimeParityGateError as exc:
            rejected[command] = exc.evidence_rejection_classification
    if len(rejected) != 3:
        raise RuntimeGateError("R3 jobs rejection contract is incomplete")
    make_parity.validate_artifact_stage(
        "cp libhoedown.a /artifacts/libhoedown.a",
        workdir=policy.workdir,
        policy=policy,
    )
    return {
        "accepted": accepted,
        "rejected": rejected,
        "jobs_policy": {"omitted_allowed": True, "minimum": 1, "maximum": 2},
        "r0_companion_event": make_observability.OBSERVATION_EVENT,
        "provider_calls": 0,
        "credential_read": False,
        "docker_executed": False,
        "checkpoint_created": False,
        "formal_attempts": 0,
        "model_tokens": 0,
        "evidence_writes": 0,
    }


def build_plan(manifest: dict[str, Any]) -> dict[str, Any]:
    protocol.validate_manifest(manifest)
    runtime = validate_runtime_gate_contract()
    return {
        "schema_version": manifest["schema_version"],
        "case_id": manifest["case"]["case_id"],
        "pair_id": manifest["schedule"][0]["pair_id"],
        "arm_order": manifest["schedule"][0]["arm_order"],
        "treatment_exposure_only": manifest["schedule"][0]["treatment_exposure_only"],
        "action_surface": manifest["runtime_parity"]["action_surface"],
        "phase_recorded_token_ceiling": manifest["budget"]["stage_maximum_recorded_tokens"],
        "checkpoint_status": manifest["checkpoint"]["status"],
        "evidence_identity_sha256": manifest["evidence"]["identity_sha256"],
        "runtime_gate": runtime,
        "execution_authorized": False,
    }


def collect_preflight_snapshot(
    manifest: dict[str, Any],
    *,
    repo_root: Path,
    host_candidate_evidence_directory: Path,
    command_runner: CommandRunner = _run_command,
) -> dict[str, Any]:
    protocol.validate_manifest(manifest, repo_root)
    candidate_name = PurePosixPath(manifest["evidence"]["directory"]).name
    expected_candidate = repo_root / ".compile-sessions" / candidate_name
    if host_candidate_evidence_directory.resolve(strict=False) != expected_candidate.resolve(strict=False):
        raise RuntimeGateError("candidate evidence directory is not bound to the frozen identity")
    branch = command_runner(("git", "branch", "--show-current"), repo_root)
    head = command_runner(("git", "rev-parse", "HEAD"), repo_root)
    origin_main = command_runner(("git", "rev-parse", "origin/main"), repo_root)
    status = command_runner(("git", "status", "--porcelain"), repo_root)
    ancestry = command_runner(("git", "merge-base", "--is-ancestor", manifest["preflight"]["authorization_baseline_commit"], "HEAD"), repo_root)
    entries = len(tuple(host_candidate_evidence_directory.iterdir())) if host_candidate_evidence_directory.exists() else 0
    snapshot = {
        "schema_version": "forge-opaque-provenance-r3-make-candidate-preflight-1.0.0",
        "branch": branch,
        "head_commit": head,
        "origin_main_commit": origin_main,
        "worktree_clean": status == "",
        "authorization_baseline_ancestor": ancestry == "",
        "frozen_parent_components": {path: _file_sha256(repo_root / path) for path in sorted(manifest["frozen_parent_components"])},
        "candidate_evidence_directory": manifest["evidence"]["directory"],
        "candidate_evidence_entries": entries,
        "checkpoint_status": manifest["checkpoint"]["status"],
        "provider_calls": 0,
        "credential_read": False,
        "docker_executed": False,
        "evidence_writes": 0,
    }
    if branch != "main" or not head or head != origin_main or status != "" or ancestry != "" or snapshot["frozen_parent_components"] != manifest["frozen_parent_components"] or entries != 0 or snapshot["checkpoint_status"] != "not_created":
        raise RuntimeGateError("R3 candidate preflight snapshot is not release-ready")
    return snapshot


def execute_checkpoint(_manifest: dict[str, Any]) -> None:
    raise RuntimeGateError("checkpoint creation is not authorized by Issue #216")


def execute_reachability(_manifest: dict[str, Any]) -> None:
    raise RuntimeGateError("reachability request is not authorized by Issue #216")


def execute_pair(_manifest: dict[str, Any]) -> None:
    raise RuntimeGateError("provider pair is not authorized by Issue #216")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "plan", "preflight"))
    parser.add_argument("--manifest", type=Path, default=protocol.DEFAULT_MANIFEST)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--host-candidate-evidence-directory", type=Path)
    args = parser.parse_args(argv)
    manifest = protocol.load_manifest(args.manifest, args.repo_root)
    if args.command == "preflight":
        if args.host_candidate_evidence_directory is None:
            raise RuntimeGateError("preflight requires the candidate evidence directory")
        result: Any = collect_preflight_snapshot(
            manifest,
            repo_root=args.repo_root,
            host_candidate_evidence_directory=args.host_candidate_evidence_directory,
        )
    elif args.command == "plan":
        result = build_plan(manifest)
    else:
        result = {
            "manifest_sha256": protocol.canonical_sha256(manifest),
            "runtime_gate": validate_runtime_gate_contract(),
            "execution_authorized": False,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

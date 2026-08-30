#!/usr/bin/env python3
"""Issue #212 R3 Make 动作可达性与 P2 构造对齐门禁。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_opaque_provenance_make_lifecycle_gate as lifecycle  # noqa: E402

SCHEMA_VERSION = "forge-opaque-provenance-r3-make-construct-alignment-gate-1.0.0"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/212"
PREREGISTRATION_PATH = (
    "benchmarks/preregistrations/"
    "cpp-opaque-provenance-r3-make-construct-alignment-gate.md"
)
R2_MANIFEST_PATH = "benchmarks/manifests/cpp-opaque-provenance-r2-make-execution.json"
R2_MANIFEST_CANONICAL_SHA256 = (
    "113192d509b3c15762f8055cb32fc9364a4a4be6bede1eeed838e540a025224e"
)

FROZEN_COMPONENTS = {
    "scripts/forge_opaque_provenance_make_reference_gate.py": (
        "5df722d6115aa879a9dbe43fb5f98278ff72df6958ae99f22fe4cb2f6d16c14a"
    ),
    "scripts/forge_opaque_provenance_make_lifecycle_gate.py": (
        "bb9fc467df0476cc1e7fdcca06bf64d020cb39f0efd48502289d814b3152230b"
    ),
    "scripts/forge_opaque_provenance_make_runtime_parity_gate.py": (
        "146e7b83d1a0afbe31928308d2a63ec000021a63755751df8ae59628a4071075"
    ),
    "scripts/forge_opaque_provenance_make_rejection_observability_gate.py": (
        "2148b8a80ba25e95baa7e1e20c6d5209bc07bb89675026f78320f5636d1737c1"
    ),
    "scripts/forge_opaque_provenance_r2_make_execution_runner.py": (
        "0854a836f347d371974594eadb32f72d0cff4361bcb06bd5e1ad2a9effef78c0"
    ),
    "scripts/forge_opaque_provenance_r2_make_result_audit.py": (
        "1deb4e47b9c85b7fc78a63e2669a4bcc2e16a22bf5c18827ba648c6671eb9ee8"
    ),
    "backend/tests/test_forge_opaque_provenance_r2_make_result_audit.py": (
        "c2293d1472da48b1a323f1a4ba9787caa8f93e2f878e7949aec2c6e83ed74bae"
    ),
    R2_MANIFEST_PATH: (
        "c25a9eca30b58e686c21a03497a0c5a163dda45ab06eaf922442a83780d7b17d"
    ),
}

SHARED_TOOL_DESCRIPTION = """在当前 R3 arm 中执行单一、非 compound 的命令。

共同动作契约：
- inspection 只能使用不改变源码、构建配置或依赖的单一命令；
- repair build 只能直接调用 make 或 gmake，effective directory 必须是
  /workspace/repo，并且只能构建 target libhoedown.a；
- jobs 可以省略，也可以设为 1 或 2；禁止无界 -j 和超过 2 的并行度；
- build 与 artifact stage 必须是两个独立动作；stage 只允许把
  /workspace/repo/libhoedown.a 复制到 /artifacts/libhoedown.a；
- command_role 必须与 inspection、build 或 artifact_stage 的动作一致。
"""


class ConstructAlignmentGateError(RuntimeError):
    """R3 Make 动作、构造身份或冻结边界无效。"""

    def __init__(self, message: str, *, classification: str) -> None:
        super().__init__(message)
        self.evidence_rejection_classification = classification
        self.evidence_action_kind = "repair_build"


@dataclass(frozen=True)
class AlignedMakePolicy:
    build_directory: str = lifecycle.WORKDIR
    target: str = lifecycle.TARGET
    maximum_jobs: int = 2


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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_frozen_components(repo_root: Path = REPO_ROOT) -> None:
    for relative_path, expected_sha256 in FROZEN_COMPONENTS.items():
        if file_sha256(repo_root / relative_path) != expected_sha256:
            raise ConstructAlignmentGateError(
                f"冻结组件发生漂移: {relative_path}",
                classification="frozen_component_drift",
            )


def validate_repair_build(
    command: str,
    *,
    workdir: str,
    policy: AlignedMakePolicy | None = None,
) -> Any:
    """验证 direct Make 身份，并将 jobs 仅作为公开的资源上限。"""

    import shlex

    current = policy or AlignedMakePolicy()
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise ConstructAlignmentGateError(
            "repair build 参数无法解析",
            classification="repair_build_arguments_invalid",
        ) from exc
    if not tokens or PurePosixPath(tokens[0]).name not in {"make", "gmake"}:
        raise ConstructAlignmentGateError(
            "repair build 必须直接调用 make 或 gmake",
            classification="repair_build_invocation_invalid",
        )
    try:
        invocation = lifecycle.reference.parse_make_invocation(
            PurePosixPath(tokens[0]).name,
            tuple(tokens[1:]),
            workdir=workdir,
        )
    except lifecycle.reference.MakeReferenceError as exc:
        raise ConstructAlignmentGateError(
            "repair build 包含未注册参数",
            classification="repair_build_arguments_invalid",
        ) from exc
    if invocation.effective_directory != current.build_directory:
        raise ConstructAlignmentGateError(
            "repair build 目录偏离冻结身份",
            classification="repair_build_directory_drift",
        )
    if invocation.target != current.target:
        raise ConstructAlignmentGateError(
            "repair build target 偏离冻结身份",
            classification="repair_build_target_drift",
        )
    if invocation.jobs == "unbounded":
        raise ConstructAlignmentGateError(
            "repair build 禁止无界 jobs",
            classification="repair_build_jobs_unbounded",
        )
    if invocation.jobs is not None and not (
        invocation.jobs.isdigit() and 1 <= int(invocation.jobs) <= current.maximum_jobs
    ):
        raise ConstructAlignmentGateError(
            "repair build jobs 超出公开资源边界",
            classification="repair_build_jobs_out_of_bounds",
        )
    return invocation


def build_arm_contract(arm: str) -> dict[str, Any]:
    if arm not in {"baseline", "treatment"}:
        raise ConstructAlignmentGateError(
            "未知实验 arm",
            classification="arm_identity_invalid",
        )
    contract: dict[str, Any] = {
        "arm": arm,
        "tool_description": SHARED_TOOL_DESCRIPTION,
        "action_surface": {
            "direct_executables": ["make", "gmake"],
            "build_directory": lifecycle.WORKDIR,
            "target": lifecycle.TARGET,
            "jobs": {"omitted_allowed": True, "minimum": 1, "maximum": 2},
            "artifact_stage": {
                "source": f"{lifecycle.WORKDIR}/{lifecycle.BUILD_OUTPUT}",
                "destination": f"/artifacts/{lifecycle.STAGED_ARTIFACT}",
                "separate_from_build": True,
            },
        },
    }
    if arm == "treatment":
        contract["repair_packet"] = lifecycle.build_repair_packet()
    return contract


def validate_gate_contract(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    validate_frozen_components(repo_root)
    manifest = json.loads((repo_root / R2_MANIFEST_PATH).read_text(encoding="utf-8"))
    preregistration_sha256 = file_sha256(repo_root / PREREGISTRATION_PATH)
    if canonical_sha256(manifest) != R2_MANIFEST_CANONICAL_SHA256:
        raise ConstructAlignmentGateError(
            "R2 Make manifest canonical identity 漂移",
            classification="frozen_component_drift",
        )
    baseline = build_arm_contract("baseline")
    treatment = build_arm_contract("treatment")
    treatment_without_packet = {
        key: value
        for key, value in treatment.items()
        if key not in {"arm", "repair_packet"}
    }
    baseline_without_arm = {
        key: value for key, value in baseline.items() if key != "arm"
    }
    if treatment_without_packet != baseline_without_arm:
        raise ConstructAlignmentGateError(
            "双臂共享工具契约不一致",
            classification="shared_action_surface_drift",
        )
    packet = treatment["repair_packet"]
    if packet != manifest["repair_packet"]["template"]:
        raise ConstructAlignmentGateError(
            "repair packet 偏离 R2 冻结内容",
            classification="repair_packet_drift",
        )
    accepted = (
        "make libhoedown.a",
        "make -j1 libhoedown.a",
        "gmake --jobs=2 libhoedown.a",
    )
    normalized = [
        asdict(
            validate_repair_build(
                command,
                workdir=lifecycle.WORKDIR,
            )
        )
        for command in accepted
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "issue_url": ISSUE_URL,
        "r2_manifest_canonical_sha256": R2_MANIFEST_CANONICAL_SHA256,
        "preregistration_sha256": preregistration_sha256,
        "frozen_components_verified": len(FROZEN_COMPONENTS),
        "shared_tool_contract_identical": True,
        "treatment_exposure_only": "repair_packet",
        "repair_packet_unchanged": True,
        "p2_identity_includes_jobs": False,
        "jobs_policy": {"omitted_allowed": True, "minimum": 1, "maximum": 2},
        "accepted_examples": normalized,
        "next_stage": "new_real_docker_lifecycle_identity_candidate",
        "provider_calls": 0,
        "credential_read": False,
        "docker_executed": False,
        "checkpoint_created": False,
        "formal_attempts": 0,
        "model_tokens": 0,
        "evidence_writes": 0,
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

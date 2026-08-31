#!/usr/bin/env python3
"""Issue #245 independent replication 的零 provider lifecycle 门禁。"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import forge_opaque_provenance_confirmatory_execution_repair_adapter as repair  # noqa: E402
import forge_opaque_provenance_confirmatory_replication_candidate_protocol as candidate  # noqa: E402

ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/245"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-opaque-provenance-confirmatory-replication-lifecycle-zero-provider-gate.md"
CANDIDATE_MANIFEST_PATH = (
    "benchmarks/manifests/cpp-opaque-provenance-confirmatory-replication-candidate.json"
)
CANDIDATE_MANIFEST_CANONICAL_SHA256 = (
    "7b1817becba4ec57eb9726be0e1faaa5427af309dca7552634e3f6a3a1b5d938"
)
CANDIDATE_MANIFEST_FILE_SHA256 = (
    "b6eb90bfc5242dec1881627101de3c0c4589c5863700293d92bec80bea2de324"
)
REPAIR_ADAPTER_SHA256 = (
    "c8a13388f6c53d308b34f013bf4a9f449190a10e779667cdf73b0e8ef1da2544"
)
ZERO_PROVIDER_ENDPOINT = "https://example.invalid/v1"
ZERO_PROVIDER_CREDENTIAL_ENV = "UNUSED_ZERO_PROVIDER_CREDENTIAL"
ZERO_PROVIDER_MODEL = "deterministic-zero-provider"


class ReplicationLifecycleGateError(RuntimeError):
    """Replication identity、零 provider 边界或 lifecycle 接线无效。"""


def load_candidate(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    path = repo_root / CANDIDATE_MANIFEST_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplicationLifecycleGateError(
            "无法读取 replication candidate manifest"
        ) from exc
    try:
        return candidate.validate_manifest(value, repo_root)
    except candidate.ReplicationCandidateError as exc:
        raise ReplicationLifecycleGateError(str(exc)) from exc


def _formal_evidence_directory(manifest: dict[str, Any]) -> Path:
    return Path(manifest["replication_candidate"]["evidence_candidate"]["directory"])


def evidence_files(directory: Path) -> list[str]:
    if not directory.exists():
        return []
    return sorted(
        str(path.relative_to(directory)).replace("\\", "/")
        for path in directory.rglob("*")
        if path.is_file()
    )


def require_empty_formal_evidence(
    manifest: dict[str, Any],
    *,
    directory: Path | None = None,
) -> list[str]:
    target = directory or _formal_evidence_directory(manifest)
    entries = evidence_files(target)
    if entries:
        raise ReplicationLifecycleGateError(
            "independent replication 正式 evidence 目录不是空目录"
        )
    return entries


def build_zero_provider_runtime_manifest(
    manifest: dict[str, Any],
    output_dir: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """构造只供 fake-model 门禁使用、不会持久化的 v1-shaped runtime。"""

    validated = candidate.validate_manifest(manifest, repo_root)
    formal = _formal_evidence_directory(validated).resolve(strict=False)
    output = output_dir.resolve(strict=False)
    if output == formal or output.is_relative_to(formal):
        raise ReplicationLifecycleGateError(
            "零 provider 门禁不得写入正式 replication evidence 目录"
        )
    parent, _parent_protocol = candidate._parent_manifest(repo_root)
    runtime = copy.deepcopy(parent)
    execution = runtime["authorized_execution"]
    execution["provider"].update(
        {
            "status": "deterministic_zero_provider_gate",
            "model": ZERO_PROVIDER_MODEL,
            "endpoint": ZERO_PROVIDER_ENDPOINT,
            "credential_env": ZERO_PROVIDER_CREDENTIAL_ENV,
            "request_timeout_seconds": 1,
            "max_retries": 0,
        }
    )
    execution["evidence"]["directory"] = str(output_dir)
    execution["evidence"]["identity_sha256"] = validated["replication_candidate"][
        "evidence_candidate"
    ]["identity_sha256"]
    runtime["authorization"] = copy.deepcopy(validated["authorization"])
    runtime["gate_context"] = {
        "issue_url": ISSUE_URL,
        "candidate_manifest_sha256": candidate.canonical_sha256(validated),
        "provider_calls_authorized": False,
        "credential_read_authorized": False,
        "model_tokens_authorized": 0,
        "formal_evidence_writes_authorized": False,
    }
    return runtime


def execute_zero_provider_pair(
    manifest: dict[str, Any],
    pair: dict[str, Any],
    pair_dir: Path,
    async_runner: Any,
    release: dict[str, str],
    *,
    model_factory: Callable[[dict[str, Any], str], Any] | None,
    formal_evidence_directory: Path | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    if model_factory is None:
        raise ReplicationLifecycleGateError(
            "零 provider 门禁要求显式 deterministic model factory"
        )
    validated = load_candidate(repo_root)
    if manifest != validated:
        raise ReplicationLifecycleGateError("执行输入不是冻结的 replication candidate")
    require_empty_formal_evidence(validated, directory=formal_evidence_directory)
    runtime = build_zero_provider_runtime_manifest(
        validated, pair_dir, repo_root=repo_root
    )
    result = repair.execute_real_pair(
        runtime,
        pair,
        pair_dir,
        async_runner,
        {"recorded_tokens": 0},
        release,
        model_factory=model_factory,
    )
    require_empty_formal_evidence(validated, directory=formal_evidence_directory)
    return result


def validate_gate_contract(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    manifest = load_candidate(repo_root)
    candidate.verify_frozen_components(manifest, repo_root)
    if candidate.canonical_sha256(manifest) != CANDIDATE_MANIFEST_CANONICAL_SHA256:
        raise ReplicationLifecycleGateError(
            "replication candidate canonical identity 发生漂移"
        )
    if (
        candidate.file_sha256(repo_root / CANDIDATE_MANIFEST_PATH)
        != CANDIDATE_MANIFEST_FILE_SHA256
    ):
        raise ReplicationLifecycleGateError(
            "replication candidate 文件 identity 发生漂移"
        )
    runtime = manifest["replication_candidate"]["runtime_candidate"]
    if runtime["runtime_file_sha256"] != REPAIR_ADAPTER_SHA256:
        raise ReplicationLifecycleGateError("repair adapter identity 发生漂移")
    if (
        candidate.file_sha256(repo_root / runtime["pair_executor_adapter"])
        != REPAIR_ADAPTER_SHA256
    ):
        raise ReplicationLifecycleGateError("repair adapter 文件发生漂移")
    preregistration = repo_root / PREREGISTRATION_PATH
    if not preregistration.is_file():
        raise ReplicationLifecycleGateError("replication lifecycle 预注册不存在")
    authorization = manifest["authorization"]
    if any(
        value for key, value in authorization.items() if key.endswith("_authorized")
    ):
        raise ReplicationLifecycleGateError("replication candidate 意外授权外部执行")
    if authorization["model_tokens_authorized"] != 0:
        raise ReplicationLifecycleGateError(
            "replication candidate 意外授权 model token"
        )
    if manifest["replication_candidate"]["relationship_to_v1"][
        "historical_outcomes_imported"
    ]:
        raise ReplicationLifecycleGateError("replication candidate 意外导入 v1 outcome")
    parent, _parent_protocol = candidate._parent_manifest(repo_root)
    repair_contract = repair.validate_contract(parent, repo_root=repo_root)
    ephemeral = build_zero_provider_runtime_manifest(
        manifest, Path("/tmp/forge-issue-245-zero-provider"), repo_root=repo_root
    )
    build_systems = {
        repair.lifecycle.build_case_adapter(pair["case_id"], repo_root).build_system
        for pair in ephemeral["schedule"]["pairs"]
    }
    if build_systems != {"cmake", "make"}:
        raise ReplicationLifecycleGateError("零 provider runtime 未覆盖 CMake 与 Make")
    return {
        "schema_version": "forge-opaque-provenance-confirmatory-replication-lifecycle-gate-1.0.0",
        "issue_url": ISSUE_URL,
        "status": "passed",
        "candidate_manifest_sha256": CANDIDATE_MANIFEST_CANONICAL_SHA256,
        "candidate_manifest_file_sha256": CANDIDATE_MANIFEST_FILE_SHA256,
        "evidence_identity_sha256": manifest["replication_candidate"][
            "evidence_candidate"
        ]["identity_sha256"],
        "schedule_identity_sha256": manifest["schedule"]["identity_sha256"],
        "case_count": repair_contract["case_count"],
        "pair_count": repair_contract["pair_count"],
        "build_systems": sorted(build_systems),
        "capture_before_commit_cleanup_required": runtime[
            "capture_before_commit_cleanup_required"
        ],
        "broad_docker_cleanup_forbidden": runtime["broad_docker_cleanup_forbidden"],
        "historical_outcomes_imported": False,
        "provider_calls": 0,
        "credential_read": False,
        "formal_attempts": 0,
        "model_tokens": 0,
        "formal_evidence_writes": 0,
        "docker_executed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate",))
    parser.parse_args(argv)
    try:
        result = validate_gate_contract()
    except (
        OSError,
        ReplicationLifecycleGateError,
        candidate.ReplicationCandidateError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

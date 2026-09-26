#!/usr/bin/env python3
"""生成、审计并校验 Stage C v4 构建入口与运行时合同修复身份。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import jsonschema

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent

import forge_stage_c_protocol as base  # noqa: E402
import forge_stage_c_task_qualification as qualification  # noqa: E402

SCHEMA_VERSION = "forge-stage-c-paired-calibration-v4-build-entrypoint-authorized-1.0.0"
DOCUMENT_TYPE = "forge_stage_c_paired_calibration_v4_build_entrypoint_authorized"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/325"
AUTHORIZATION_BASELINE_COMMIT = "cbb29c2473fdb0814ed4a47bdd7ea4f06fc21f28"
V3_MANIFEST_PATH = (
    "benchmarks/manifests/cpp-stage-c-paired-calibration-v3-pair-source-authorized.json"
)
V3_PROTOCOL_PATH = "scripts/forge_stage_c_v3_protocol.py"
V3_FAILURE_AUDIT_PATH = (
    "benchmarks/reports/cpp-stage-c-paired-calibration-v3-failed.json"
)
V3_FAILURE_REPORT_PATH = (
    "benchmarks/reports/cpp-stage-c-paired-calibration-v3-failed.md"
)
SOURCE_STRUCTURE_AUDIT_PATH = (
    "benchmarks/reports/cpp-stage-c-v4-source-structure-audit.json"
)
PREREGISTRATION_PATH = (
    "benchmarks/preregistrations/cpp-stage-c-paired-calibration-v4-build-entrypoint.md"
)
PROTOCOL_PATH = "scripts/forge_stage_c_v4_protocol.py"
RUNNER_PATH = "scripts/forge_stage_c_runner.py"
OPERATIONS_PATH = "backend/packages/harness/deerflow/compile/operations.py"
MANIFEST_RELATIVE_PATH = "benchmarks/manifests/cpp-stage-c-paired-calibration-v4-build-entrypoint-authorized.json"
SCHEMA_RELATIVE_PATH = "benchmarks/schemas/forge-stage-c-paired-calibration-v4-build-entrypoint-authorized.schema.json"
DEFAULT_EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-stage-c-paired-calibration-v4-build-entrypoint"
V3_EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-stage-c-paired-calibration-v3-pair-source"
DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_RELATIVE_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_RELATIVE_PATH

V3_MANIFEST_FILE_SHA256 = (
    "00f1e29a453b8663d2f55d5e82a5a6e19ce308506f867c47dc3589e7f854b5c2"
)
V3_MANIFEST_SHA256 = "410f32b0a2cf22eac9023c80da18876adee5fbd6f2abd689eac37ce63e8f2b29"
V3_RUNNER_SHA256 = "cfb033b25f3d658879e8f8be1f16e67ee4bd91f786e9d48252a6cd718f8345d7"
V3_RELEASE_REVISION = "cbb29c2473fdb0814ed4a47bdd7ea4f06fc21f28"

_BUILD_SYSTEM_MARKERS = {
    "cmake": ("CMakeLists.txt",),
    "make": ("Makefile", "GNUmakefile", "makefile"),
    "autotools": ("configure", "configure.ac", "configure.in", "autogen.sh"),
}

canonical_sha256 = base.canonical_sha256
file_sha256 = base.file_sha256


class StageCV4ProtocolError(RuntimeError):
    """Stage C v4 审计、manifest 或授权边界无效。"""


def _load_v3_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    path = repo_root / V3_MANIFEST_PATH
    value = qualification.load_json(path)
    if (
        file_sha256(path) != V3_MANIFEST_FILE_SHA256
        or canonical_sha256(value) != V3_MANIFEST_SHA256
    ):
        raise StageCV4ProtocolError("Stage C v3 manifest identity 漂移")
    return value


def _file_inventory(root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {
        "file_count": len(files),
        "total_size_bytes": sum(item["size_bytes"] for item in files),
        "files": files,
    }


def _zero_managed_resources() -> bool:
    containers = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    images = subprocess.run(
        ["docker", "images", "-q", "--filter", "label=forge.stage-c.managed=true"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return not images and not any(
        name.startswith("forge-stage-c-") for name in containers
    )


def capture_v3_failure_audit(
    evidence_directory: Path = Path(V3_EVIDENCE_DIRECTORY),
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    if not evidence_directory.is_dir():
        raise StageCV4ProtocolError("Stage C v3 evidence 目录不存在")
    pair_path = evidence_directory / "pairs/stage-c-v3-json-c-r1/pair.json"
    reachability_path = evidence_directory / "reports/reachability.json"
    pair = qualification.load_json(pair_path)
    reachability = qualification.load_json(reachability_path)
    pair_files = sorted(evidence_directory.glob("pairs/*/pair.json"))
    incomplete_pair_dirs = sorted(
        path.name
        for path in (evidence_directory / "pairs").glob("*")
        if path.is_dir() and not (path / "pair.json").is_file()
    )
    if (
        [path.relative_to(evidence_directory).as_posix() for path in pair_files]
        != ["pairs/stage-c-v3-json-c-r1/pair.json"]
        or incomplete_pair_dirs
        or pair.get("complete") is not True
        or pair.get("manifest_sha256") != V3_MANIFEST_SHA256
        or reachability.get("passed") is not True
        or reachability.get("manifest_sha256") != V3_MANIFEST_SHA256
    ):
        raise StageCV4ProtocolError("Stage C v3 evidence 前缀无效")
    arms = pair["arms"]
    formal_tokens = sum(arm["recorded_tokens"] for arm in arms)
    formal_requests = sum(arm["model_requests"] for arm in arms)
    inventory = _file_inventory(evidence_directory)
    audit = {
        "schema_version": "forge-stage-c-paired-calibration-v3-failed-audit-1.0.0",
        "document_type": "forge_stage_c_paired_calibration_v3_failed_audit",
        "classification": "completed_pair_then_next_pair_source_build_system_validation_rejected_before_registration",
        "identity": {
            "manifest_file_sha256": V3_MANIFEST_FILE_SHA256,
            "manifest_sha256": V3_MANIFEST_SHA256,
            "release_revision": V3_RELEASE_REVISION,
            "runner_sha256": V3_RUNNER_SHA256,
        },
        "evidence_directory": V3_EVIDENCE_DIRECTORY,
        "reachability": {
            "passed": True,
            "request_count": reachability["request_count"],
            "recorded_tokens": reachability["recorded_tokens"],
            "marker_sha256": file_sha256(
                evidence_directory / "markers/reachability.json"
            ),
            "report_sha256": file_sha256(reachability_path),
        },
        "completed_prefix": {
            "pair_count": 1,
            "formal_arm_attempts": 2,
            "pair_id": pair["pair_id"],
            "pair_result_sha256": file_sha256(pair_path),
            "arms": [
                {
                    "arm": arm["arm"],
                    "attempt_id": arm["attempt_id"],
                    "model_requests": arm["model_requests"],
                    "recorded_tokens": arm["recorded_tokens"],
                    "strict_reproducible_build_success": arm[
                        "strict_reproducible_build_success"
                    ],
                    "error_class": arm["error_class"],
                    "attempt_sha256": file_sha256(
                        evidence_directory
                        / f"pairs/{pair['pair_id']}/{arm['arm']}/attempt.json"
                    ),
                    "result_sha256": file_sha256(
                        evidence_directory
                        / f"pairs/{pair['pair_id']}/{arm['arm']}/result.json"
                    ),
                }
                for arm in arms
            ],
        },
        "next_pair_failure": {
            "pair_id": "stage-c-v3-stockfish-11-r1",
            "task_id": "stockfish-11",
            "phase": "pair_source_validation_before_first_arm_attempt_marker",
            "error_class": "StageCRunnerError",
            "error_message": "stockfish-11 build-system identity 漂移",
            "pair_directory_exists": False,
            "attempt_exists": False,
            "result_exists": False,
            "observation_source": "operator_terminal_trace_and_exact_source_structure_audit",
        },
        "usage": {
            "formal_arm_attempts": 2,
            "formal_arm_model_requests": formal_requests,
            "formal_arm_recorded_tokens": formal_tokens,
            "provider_calls_including_reachability": formal_requests
            + reachability["request_count"],
            "recorded_tokens_including_reachability": formal_tokens
            + reachability["recorded_tokens"],
        },
        "batch": {
            "marker_sha256": file_sha256(evidence_directory / "markers/batch.json"),
            "complete_pair_count": 1,
            "incomplete_pair_count": 0,
            "must_not_resume": True,
        },
        "resource_audit": {"zero_managed_resources": _zero_managed_resources()},
        "evidence_inventory": inventory,
        "interpretation": {
            "historical_outcomes_imported": False,
            "v3_identity_closed": True,
            "v4_requires_fresh_pair_and_attempt_ids": True,
        },
    }
    if audit["resource_audit"]["zero_managed_resources"] is not True:
        raise StageCV4ProtocolError("Stage C v3 存在 managed resource 残留")
    path = repo_root / V3_FAILURE_AUDIT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return audit


def _git_environment() -> dict[str, str]:
    env = os.environ.copy()
    for source_name, target_name in (
        ("COMPILE_RUNTIME_HTTP_PROXY", "HTTP_PROXY"),
        ("COMPILE_RUNTIME_HTTPS_PROXY", "HTTPS_PROXY"),
        ("COMPILE_RUNTIME_NO_PROXY", "NO_PROXY"),
    ):
        value = os.environ.get(source_name)
        if value:
            env[target_name] = value
    return env


def _fetch_source(task: dict[str, Any], destination: Path) -> Path:
    repository = destination / "repository"
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "remote",
            "add",
            "origin",
            task["repository_url"],
        ],
        check=True,
    )
    argv = [
        "git",
        "-c",
        "http.version=HTTP/1.1",
        "-C",
        str(repository),
        "fetch",
        "--quiet",
        "--depth",
        "1",
        "origin",
        task["commit_sha"],
    ]
    for attempt in range(1, 4):
        result = subprocess.run(argv, check=False, env=_git_environment())
        if result.returncode == 0:
            break
        if attempt == 3:
            raise StageCV4ProtocolError(f"{task['task_id']} source audit fetch 失败")
        time.sleep(attempt)
    subprocess.run(
        ["git", "-C", str(repository), "checkout", "--quiet", "--detach", "FETCH_HEAD"],
        check=True,
    )
    if qualification._archive_sha256(repository) != task["source_snapshot_sha256"]:
        raise StageCV4ProtocolError(f"{task['task_id']} source audit snapshot 漂移")
    source = destination / "source"
    source.mkdir()
    archive = subprocess.Popen(
        ["git", "-C", str(repository), "archive", "--format=tar", "HEAD"],
        stdout=subprocess.PIPE,
    )
    extract = subprocess.run(
        ["tar", "-xf", "-", "-C", str(source)],
        stdin=archive.stdout,
        check=False,
    )
    if archive.stdout is not None:
        archive.stdout.close()
    if extract.returncode != 0 or archive.wait() != 0:
        raise StageCV4ProtocolError(f"{task['task_id']} source audit export 失败")
    return source


def _detect_source_markers(source: Path) -> dict[str, list[str]]:
    top_level = {
        build_system: [marker for marker in markers if (source / marker).is_file()]
        for build_system, markers in _BUILD_SYSTEM_MARKERS.items()
    }
    top_level = {key: value for key, value in top_level.items() if value}
    if top_level:
        return top_level
    nested = {}
    for build_system, markers in _BUILD_SYSTEM_MARKERS.items():
        paths = sorted(
            path.relative_to(source).as_posix()
            for child in source.iterdir()
            if child.is_dir()
            for marker in markers
            if (path := child / marker).is_file()
        )
        if paths:
            nested[build_system] = paths
    return nested


def capture_source_structure_audit(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    manifest = _load_v3_manifest(repo_root)
    tasks = {task["task_id"]: task for task in manifest["tasks"]}
    observations = []
    for task_id in manifest["schedule"]["project_order"]:
        task = tasks[task_id]
        with tempfile.TemporaryDirectory(
            prefix=f"forge-stage-c-v4-source-audit-{task_id}-"
        ) as temporary:
            source = _fetch_source(task, Path(temporary))
            markers = _detect_source_markers(source)
        selected = task["selected_build_system"]
        if selected not in markers:
            raise StageCV4ProtocolError(f"{task_id} selected build system marker 缺失")
        observations.append(
            {
                "task_id": task_id,
                "commit_sha": task["commit_sha"],
                "source_snapshot_sha256": task["source_snapshot_sha256"],
                "declared_capabilities": task["build_system_capabilities"],
                "selected_build_system": selected,
                "detected_markers": markers,
                "selected_marker": markers[selected][0],
                "passed": True,
            }
        )
    audit = {
        "schema_version": "forge-stage-c-v4-source-structure-audit-1.0.0",
        "document_type": "forge_stage_c_v4_source_structure_audit",
        "manifest_sha256": V3_MANIFEST_SHA256,
        "scope": "all_12_exact_sources_top_level_then_one_subdirectory",
        "provider_calls": 0,
        "model_tokens": 0,
        "formal_stage_c_attempts": 0,
        "task_count": len(observations),
        "tasks": observations,
    }
    path = repo_root / SOURCE_STRUCTURE_AUDIT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return audit


def _validate_v3_failure_audit(repo_root: Path) -> dict[str, Any]:
    value = qualification.load_json(repo_root / V3_FAILURE_AUDIT_PATH)
    if (
        value.get("schema_version")
        != "forge-stage-c-paired-calibration-v3-failed-audit-1.0.0"
        or value.get("classification")
        != "completed_pair_then_next_pair_source_build_system_validation_rejected_before_registration"
        or value.get("identity")
        != {
            "manifest_file_sha256": V3_MANIFEST_FILE_SHA256,
            "manifest_sha256": V3_MANIFEST_SHA256,
            "release_revision": V3_RELEASE_REVISION,
            "runner_sha256": V3_RUNNER_SHA256,
        }
        or value.get("usage")
        != {
            "formal_arm_attempts": 2,
            "formal_arm_model_requests": 3,
            "formal_arm_recorded_tokens": 30_689,
            "provider_calls_including_reachability": 4,
            "recorded_tokens_including_reachability": 30_768,
        }
        or value.get("batch", {}).get("must_not_resume") is not True
        or value.get("next_pair_failure", {}).get("attempt_exists") is not False
        or value.get("resource_audit", {}).get("zero_managed_resources") is not True
        or value.get("interpretation", {}).get("historical_outcomes_imported")
        is not False
    ):
        raise StageCV4ProtocolError("Stage C v3 失败审计语义无效")
    inventory = value.get("evidence_inventory", {})
    files = inventory.get("files")
    if (
        not isinstance(files, list)
        or inventory.get("file_count") != 243
        or len(files) != 243
        or inventory.get("total_size_bytes") != 1_514_018
        or len({item.get("path") for item in files if isinstance(item, dict)}) != 243
    ):
        raise StageCV4ProtocolError("Stage C v3 evidence inventory 无效")
    return value


def _validate_source_structure_audit(repo_root: Path) -> dict[str, Any]:
    value = qualification.load_json(repo_root / SOURCE_STRUCTURE_AUDIT_PATH)
    v3 = _load_v3_manifest(repo_root)
    tasks = {task["task_id"]: task for task in v3["tasks"]}
    observations = value.get("tasks")
    if (
        value.get("schema_version") != "forge-stage-c-v4-source-structure-audit-1.0.0"
        or value.get("manifest_sha256") != V3_MANIFEST_SHA256
        or value.get("task_count") != 12
        or not isinstance(observations, list)
        or len(observations) != 12
    ):
        raise StageCV4ProtocolError("Stage C v4 source structure audit 无效")
    for observation in observations:
        task = tasks.get(observation.get("task_id"))
        selected = observation.get("selected_build_system")
        markers = observation.get("detected_markers", {})
        if (
            task is None
            or observation.get("commit_sha") != task["commit_sha"]
            or observation.get("source_snapshot_sha256")
            != task["source_snapshot_sha256"]
            or selected != task["selected_build_system"]
            or not isinstance(markers.get(selected), list)
            or observation.get("selected_marker") not in markers[selected]
            or observation.get("passed") is not True
        ):
            raise StageCV4ProtocolError("Stage C v4 task source structure audit 漂移")
    stockfish = next(item for item in observations if item["task_id"] == "stockfish-11")
    if stockfish["selected_marker"] != "src/Makefile":
        raise StageCV4ProtocolError("Stockfish 嵌套构建入口未冻结")
    return value


def _v4_schedule(schedule: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(schedule)
    value["pairs"] = []
    for pair in schedule["pairs"]:
        updated = copy.deepcopy(pair)
        pair_id = f"stage-c-v4-{pair['task_id']}-r{pair['replicate']}"
        updated["pair_id"] = pair_id
        updated["attempt_ids"] = {arm: f"{pair_id}-{arm.lower()}" for arm in ("A", "B")}
        value["pairs"].append(updated)
    value["source_preparation_fetch_max_attempts"] = 3
    value["build_system_marker_fallback_depth"] = 1
    value["v3_outcomes_imported"] = False
    return value


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    prior = _validate_v3_failure_audit(repo_root)
    source_audit = _validate_source_structure_audit(repo_root)
    manifest = copy.deepcopy(_load_v3_manifest(repo_root))
    preregistration = repo_root / PREREGISTRATION_PATH
    if not preregistration.is_file():
        raise StageCV4ProtocolError("Stage C v4 预注册不存在")
    manifest["$schema"] = (
        "../schemas/forge-stage-c-paired-calibration-v4-build-entrypoint-authorized.schema.json"
    )
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["document_type"] = DOCUMENT_TYPE
    manifest["issue_url"] = ISSUE_URL
    manifest["purpose"] = "stage_c_controlled_paired_calibration_v4_build_entrypoint"
    manifest["schedule"] = _v4_schedule(manifest["schedule"])
    manifest["analysis"]["v3_outcomes_imported"] = False
    manifest["authorization"]["prior_actual_recorded_tokens"] = 72_769
    manifest["authorization"]["cumulative_max_recorded_tokens"] = 14_477_769
    manifest["execution"].update(
        {
            "authorization_baseline_commit": AUTHORIZATION_BASELINE_COMMIT,
            "evidence_directory": DEFAULT_EVIDENCE_DIRECTORY,
            "source_fetch_max_attempts_before_registration": 3,
            "build_system_marker_fallback_depth": 1,
            "oracle_artifact_source": "candidate_image",
            "v3_evidence_imported": False,
        }
    )
    manifest["preregistration"] = {
        "path": PREREGISTRATION_PATH,
        "file_sha256": file_sha256(preregistration),
    }
    manifest["prior_failed_identity"] = {
        "audit_path": V3_FAILURE_AUDIT_PATH,
        "audit_file_sha256": file_sha256(repo_root / V3_FAILURE_AUDIT_PATH),
        "audit_canonical_sha256": canonical_sha256(prior),
        "manifest_path": V3_MANIFEST_PATH,
        "manifest_file_sha256": V3_MANIFEST_FILE_SHA256,
        "manifest_sha256": V3_MANIFEST_SHA256,
        "release_revision": V3_RELEASE_REVISION,
        "evidence_directory": V3_EVIDENCE_DIRECTORY,
        "must_not_resume": True,
        "historical_outcomes_imported": False,
    }
    manifest["source_structure_audit"] = {
        "path": SOURCE_STRUCTURE_AUDIT_PATH,
        "file_sha256": file_sha256(repo_root / SOURCE_STRUCTURE_AUDIT_PATH),
        "canonical_sha256": canonical_sha256(source_audit),
        "task_count": 12,
        "stockfish_build_marker": "src/Makefile",
    }
    frozen = manifest["frozen_components"]
    frozen.pop(RUNNER_PATH, None)
    for relative in (
        V3_MANIFEST_PATH,
        V3_PROTOCOL_PATH,
        V3_FAILURE_AUDIT_PATH,
        V3_FAILURE_REPORT_PATH,
        SOURCE_STRUCTURE_AUDIT_PATH,
        PREREGISTRATION_PATH,
        PROTOCOL_PATH,
        RUNNER_PATH,
        OPERATIONS_PATH,
    ):
        frozen[relative] = file_sha256(repo_root / relative)
    return manifest


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": (
            "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-stage-c-paired-calibration-v4-build-entrypoint-authorized.schema.json"
        ),
        "title": "Forge Stage C paired calibration v4 build entrypoint authorized",
        "const": manifest,
    }


def validate_manifest(
    value: dict[str, Any],
    repo_root: Path = REPO_ROOT,
    *,
    check_schema_file: bool = True,
) -> dict[str, Any]:
    expected = generate_manifest(repo_root)
    if value != expected:
        raise StageCV4ProtocolError("Stage C v4 manifest 与确定性生成结果不一致")
    schedule = value["schedule"]
    if (
        len(schedule["pairs"]) != 24
        or any(
            not pair["pair_id"].startswith("stage-c-v4-") for pair in schedule["pairs"]
        )
        or schedule.get("source_preparation_fetch_max_attempts") != 3
        or schedule.get("build_system_marker_fallback_depth") != 1
        or schedule.get("retry") is not False
        or schedule.get("replacement") is not False
        or schedule.get("backfill") is not False
    ):
        raise StageCV4ProtocolError("Stage C v4 schedule 边界无效")
    schema = generate_schema(expected)
    jsonschema.Draft202012Validator.check_schema(schema)
    if check_schema_file:
        if (
            not DEFAULT_SCHEMA.is_file()
            or qualification.load_json(DEFAULT_SCHEMA) != schema
        ):
            raise StageCV4ProtocolError("Stage C v4 const Schema 缺失或漂移")
        jsonschema.validate(value, qualification.load_json(DEFAULT_SCHEMA))
    return value


def load_manifest(
    path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    return validate_manifest(qualification.load_json(path), repo_root)


def release_revision(repo_root: Path = REPO_ROOT) -> str:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    ancestor = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            AUTHORIZATION_BASELINE_COMMIT,
            revision,
        ],
        cwd=repo_root,
        check=False,
    )
    if ancestor.returncode != 0:
        raise StageCV4ProtocolError(
            "当前 release 不是 Stage C v4 authorization baseline 的后代"
        )
    return revision


def write_generated(manifest: dict[str, Any]) -> None:
    DEFAULT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_SCHEMA.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    DEFAULT_SCHEMA.write_text(
        json.dumps(
            generate_schema(manifest), ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "capture-v3-audit",
            "capture-source-audit",
            "generate",
            "validate",
            "show-schedule",
        ),
    )
    parser.add_argument(
        "--evidence-directory",
        type=Path,
        default=Path(V3_EVIDENCE_DIRECTORY),
    )
    args = parser.parse_args(argv)
    if args.command == "capture-v3-audit":
        result: Any = capture_v3_failure_audit(args.evidence_directory)
    elif args.command == "capture-source-audit":
        result = capture_source_structure_audit()
    elif args.command == "generate":
        manifest = generate_manifest()
        write_generated(manifest)
        result = {
            "status": "generated",
            "manifest_sha256": canonical_sha256(manifest),
            "pair_count": 24,
            "physical_attempt_count": 48,
        }
    else:
        manifest = load_manifest()
        if args.command == "validate":
            result = {
                "status": "valid",
                "manifest_sha256": canonical_sha256(manifest),
                "release_revision": release_revision(),
                "provider_calls": 0,
                "formal_stage_c_attempts": 0,
                "model_tokens": 0,
            }
        else:
            result = manifest["schedule"]
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

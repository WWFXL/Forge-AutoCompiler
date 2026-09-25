#!/usr/bin/env python3
"""Issue #289 单 Agent Workflow Node Phase 5 未授权校准协议。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import jsonschema

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent

SCHEMA_VERSION = "forge-agent-workflow-stage-b-calibration-candidate-1.0.0"
DOCUMENT_TYPE = "forge_agent_workflow_stage_b_calibration_candidate"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/289"
BASELINE_COMMIT = "5129cccf46d6ff7afd92e9978e0efc7967ac29c8"
MANIFEST_RELATIVE_PATH = "benchmarks/manifests/cpp-agent-workflow-stage-b-calibration-candidate.json"
SCHEMA_RELATIVE_PATH = "benchmarks/schemas/forge-agent-workflow-stage-b-calibration-candidate.schema.json"
PREREGISTRATION_PATH = "benchmarks/preregistrations/cpp-agent-workflow-stage-b-calibration-candidate.md"
HISTORICAL_FIXTURE_PATH = "benchmarks/fixtures/cxxcrafter-stage-b-adjudication-v1.json"
PROTOCOL_PATH = "scripts/forge_agent_workflow_stage_b_calibration_protocol.py"
RUNNER_PATH = "scripts/forge_agent_workflow_stage_b_calibration_runner.py"
EVIDENCE_DIRECTORY = "/workspace/.compile-sessions/benchmark-evidence-agent-workflow-stage-b-calibration-v1"
SOURCE_ADJUDICATION_REPOSITORY = "CXXCrafter-Community-Edition"
SOURCE_ADJUDICATION_PATH = "benchmark/reports/stage-b-external-adjudication-v1.json"
SOURCE_ADJUDICATION_SHA256 = "7e724e5a9f2ed98836d42ad2521bbbaad316b7f53fc3c16001032380bb2c1c7e"

DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_RELATIVE_PATH
DEFAULT_SCHEMA = REPO_ROOT / SCHEMA_RELATIVE_PATH

TASKS: tuple[dict[str, Any], ...] = (
    {
        "task_id": "yyjson",
        "repository_url": "https://github.com/ibireme/yyjson.git",
        "commit_sha": "9365ddc7061033df656578bf86040048b5b5531a",
        "build_system": "cmake",
        "target_contract": {
            "target_id": "yyjson-static-library",
            "artifact_types": ["static_library"],
            "artifact_path_patterns": ["libyyjson.a"],
            "functional_oracle_ref": "stage-b-yyjson-consumer-v1",
        },
        "required_candidate_artifacts": ["libyyjson.a", "include/yyjson.h"],
        "oracle": {
            "kind": "compile_and_run",
            "language": "c11",
            "source": '#include <yyjson.h>\nint main(void) { yyjson_doc *doc = yyjson_read("null", 4, 0); if (!doc) return 1; yyjson_doc_free(doc); return 0; }\n',
            "compile_argv": ["cc", "-std=c11", "-I/artifacts/include", "{source}", "/artifacts/libyyjson.a", "-o", "{executable}"],
            "run_argv": ["{executable}"],
        },
    },
    {
        "task_id": "cppitertools",
        "repository_url": "https://github.com/ryanhaining/cppitertools.git",
        "commit_sha": "531b3d753d2bbfe3b0ababe61c2e95e965c54a66",
        "build_system": "cmake",
        "target_contract": {
            "target_id": "cppitertools-consumer",
            "artifact_types": ["executable"],
            "artifact_path_patterns": ["cppitertools-consumer"],
            "functional_oracle_ref": "stage-b-cppitertools-consumer-v1",
        },
        "required_candidate_artifacts": ["cppitertools-consumer", "cppitertools/range.hpp"],
        "oracle": {
            "kind": "compile_and_run",
            "language": "c++17",
            "source": "#include <cppitertools/range.hpp>\nint main() { int sum = 0; for (int value : iter::range(4)) sum += value; return sum == 6 ? 0 : 1; }\n",
            "compile_argv": ["c++", "-std=c++17", "-I/artifacts", "{source}", "-o", "{executable}"],
            "run_argv": ["{executable}"],
        },
    },
    {
        "task_id": "openh264",
        "repository_url": "https://github.com/cisco/openh264.git",
        "commit_sha": "4a2615fac570c6ca1ed4f157b9fdab9466edfd80",
        "build_system": "make",
        "target_contract": {
            "target_id": "openh264-static-library",
            "artifact_types": ["static_library"],
            "artifact_path_patterns": ["libopenh264.a"],
            "functional_oracle_ref": "stage-b-openh264-consumer-v1",
        },
        "required_candidate_artifacts": ["libopenh264.a", "include/wels/codec_api.h", "include/wels/codec_app_def.h", "include/wels/codec_def.h"],
        "oracle": {
            "kind": "compile_and_run",
            "language": "c++17",
            "source": "#include <wels/codec_api.h>\nint main() { ISVCEncoder *encoder = nullptr; if (WelsCreateSVCEncoder(&encoder) != 0 || !encoder) return 1; WelsDestroySVCEncoder(encoder); return 0; }\n",
            "compile_argv": ["c++", "-std=c++17", "-I/artifacts/include", "{source}", "/artifacts/libopenh264.a", "-lpthread", "-lm", "-o", "{executable}"],
            "run_argv": ["{executable}"],
        },
    },
    {
        "task_id": "uwebsockets",
        "repository_url": "https://github.com/uNetworking/uWebSockets.git",
        "commit_sha": "fe7c01a477b688a7743f754fee33bdd78d52ad91",
        "build_system": "make",
        "target_contract": {
            "target_id": "uwebsockets-hello-world",
            "artifact_types": ["executable"],
            "artifact_path_patterns": ["HelloWorld"],
            "functional_oracle_ref": "stage-b-uwebsockets-http-v3",
        },
        "required_candidate_artifacts": ["HelloWorld", "uSockets/uSockets.a"],
        "oracle": {
            "kind": "service_probe",
            "start_argv": ["./HelloWorld"],
            "workdir": "/artifacts",
            "listen_host": "127.0.0.1",
            "listen_port": 3000,
            "startup_timeout_seconds": 10,
            "probe": {"scheme": "http", "path": "/", "expected_status": 200},
        },
    },
    {
        "task_id": "c-ares",
        "repository_url": "https://github.com/c-ares/c-ares.git",
        "commit_sha": "589b5887d47736e5b70a1fddaf9bf90297adde65",
        "build_system": "autotools",
        "target_contract": {
            "target_id": "cares-shared-library",
            "artifact_types": ["shared_library"],
            "artifact_path_patterns": ["lib/libcares.so"],
            "functional_oracle_ref": "stage-b-cares-consumer-v1",
        },
        "required_candidate_artifacts": ["lib/libcares.so", "include/ares.h", "include/ares_build.h", "include/ares_rules.h", "include/ares_version.h"],
        "oracle": {
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <ares.h>\nint main(void) { if (ares_library_init(ARES_LIB_INIT_ALL) != ARES_SUCCESS) return 1; ares_library_cleanup(); return 0; }\n",
            "compile_argv": ["cc", "-std=c11", "{source}", "-I/artifacts/include", "-L/artifacts/lib", "-Wl,-rpath,/artifacts/lib", "-lcares", "-o", "{executable}"],
            "run_argv": ["{executable}"],
        },
    },
    {
        "task_id": "libass",
        "repository_url": "https://github.com/libass/libass.git",
        "commit_sha": "f9fd3d20dff1cd84b7c74c8ae7f79711ad7736fa",
        "build_system": "autotools",
        "target_contract": {
            "target_id": "libass-shared-library",
            "artifact_types": ["shared_library"],
            "artifact_path_patterns": ["lib/libass.so.9.4.2"],
            "functional_oracle_ref": "stage-b-libass-consumer-v1",
        },
        "required_candidate_artifacts": ["lib/libass.so.9.4.2", "lib/libass.a", "include/ass/ass.h", "include/ass/ass_types.h"],
        "oracle": {
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <ass/ass.h>\nint main(void) { ASS_Library *library = ass_library_init(); if (!library) return 1; ass_library_done(library); return 0; }\n",
            "compile_argv": ["cc", "-std=c11", "{source}", "-I/artifacts/include", "-L/artifacts/lib", "-Wl,-rpath,/artifacts/lib", "-lass", "-o", "{executable}"],
            "run_argv": ["{executable}"],
        },
    },
)


class Phase5ProtocolError(RuntimeError):
    """Phase 5 校准身份、授权边界或历史审计发生漂移。"""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frozen_components(repo_root: Path) -> dict[str, str]:
    paths = (
        PREREGISTRATION_PATH,
        HISTORICAL_FIXTURE_PATH,
        PROTOCOL_PATH,
        RUNNER_PATH,
        "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py",
        "backend/packages/harness/deerflow/compile/external_evaluator.py",
        "backend/tests/test_agent_workflow_phase4_docker.py",
    )
    return {path: file_sha256(repo_root / path) for path in paths}


def audit_historical_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    source = fixture.get("source")
    expected_source = {
        "repository": SOURCE_ADJUDICATION_REPOSITORY,
        "path": SOURCE_ADJUDICATION_PATH,
        "sha256": SOURCE_ADJUDICATION_SHA256,
        "historical_evidence_mutated": False,
        "scope": "CXXCrafter Stage B 六项目历史轨迹的只读综合判定快照",
    }
    if source != expected_source:
        raise Phase5ProtocolError("历史 Stage B 综合裁决来源发生漂移")
    if fixture.get("selection_policy") != {
        "default_evaluation_run": "stage-b-external-v2",
        "overrides": {"uwebsockets": "stage-b-external-uwebsockets-v3"},
    }:
        raise Phase5ProtocolError("历史 Stage B evaluator 选择策略发生漂移")
    tasks = fixture.get("tasks")
    if not isinstance(tasks, list) or [task.get("task_id") for task in tasks] != [task["task_id"] for task in TASKS]:
        raise Phase5ProtocolError("历史 Stage B task 顺序或集合发生漂移")
    expected = {task["task_id"]: task for task in TASKS}
    for task in tasks:
        frozen = expected[task["task_id"]]
        if task.get("commit_sha") != frozen["commit_sha"] or task.get("build_system") != frozen["build_system"]:
            raise Phase5ProtocolError(f"历史 Stage B identity 发生漂移: {task['task_id']}")
        expected_evaluation_run = "stage-b-external-uwebsockets-v3" if task["task_id"] == "uwebsockets" else "stage-b-external-v2"
        if task.get("selected_evaluation_run") != expected_evaluation_run:
            raise Phase5ProtocolError(f"历史 Stage B evaluator identity 发生漂移: {task['task_id']}")
    return {
        "task_count": len(tasks),
        "candidate_generated": sum(task["candidate_generated"] is True for task in tasks),
        "candidate_submitted": sum(task["candidate_submitted"] is True for task in tasks),
        "strict_success": sum(task["strict_success"] is True for task in tasks),
        "bitwise_reproducible": sum(task["bitwise_reproducible"] is True for task in tasks),
        "candidate_to_submit_gap": [task["task_id"] for task in tasks if task["candidate_generated"] and not task["candidate_submitted"]],
        "evaluator_v3_overrides": [task["task_id"] for task in tasks if task["selected_evaluation_run"] == "stage-b-external-uwebsockets-v3"],
    }


def load_historical_fixture(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    try:
        fixture = json.loads((repo_root / HISTORICAL_FIXTURE_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase5ProtocolError("无法读取历史 Stage B audit fixture") from exc
    summary = audit_historical_fixture(fixture)
    if summary != {
        "task_count": 6,
        "candidate_generated": 6,
        "candidate_submitted": 4,
        "strict_success": 6,
        "bitwise_reproducible": 5,
        "candidate_to_submit_gap": ["cppitertools", "uwebsockets"],
        "evaluator_v3_overrides": ["uwebsockets"],
    }:
        raise Phase5ProtocolError("历史 Stage B 四层汇总发生漂移")
    return fixture


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    fixture = load_historical_fixture(repo_root)
    return {
        "$schema": "../schemas/forge-agent-workflow-stage-b-calibration-candidate.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "issue_url": ISSUE_URL,
        "status": "candidate_not_authorized",
        "baseline_commit": BASELINE_COMMIT,
        "purpose": "engineering_calibration_only",
        "authorization": {
            "provider_calls_authorized": False,
            "credential_read_authorized": False,
            "model_creation_authorized": False,
            "reachability_request_authorized": False,
            "docker_execution_authorized": False,
            "evidence_write_authorized": False,
            "formal_attempts_authorized": False,
            "model_tokens_authorized": 0,
        },
        "historical_baseline": {
            "fixture_path": HISTORICAL_FIXTURE_PATH,
            "fixture_sha256": file_sha256(repo_root / HISTORICAL_FIXTURE_PATH),
            "source_adjudication_sha256": fixture["source"]["sha256"],
            "outcomes_imported": False,
            "historical_evidence_mutated": False,
            "audit": audit_historical_fixture(fixture),
        },
        "provider_candidate": {
            "profile": "deepseek-flash",
            "provider": "deepseek",
            "endpoint": "https://api.deepseek.com",
            "credential_env_name": "DEEPSEEK_API_KEY",
            "request_timeout_seconds": 300,
            "model_max_retries": 0,
            "fallback_enabled": False,
        },
        "environment_candidate": {
            "compile_image": "autocompiler:gcc13",
            "image_id": None,
            "parallel_jobs": 4,
            "network_policy": "compile-network-v1",
            "image_id_must_be_frozen_by_authorized_amendment": True,
        },
        "budget_candidate": {
            "per_task": {
                "max_model_requests": 24,
                "max_recorded_tokens": 300000,
                "max_agent_steps": 64,
                "max_tool_calls": 48,
                "max_commands": 32,
                "node_timeout_seconds": 1800,
                "command_timeout_seconds": 900,
                "evaluator_timeout_seconds": 1800,
                "replay_timeout_seconds": 1800,
                "cleanup_timeout_seconds": 120,
            },
            "batch_max_recorded_tokens": 1800000,
            "budget_checked_between_attempts_only": True,
        },
        "schedule": {
            "order": [task["task_id"] for task in TASKS],
            "attempts_per_task": 1,
            "replacement": False,
            "backfill": False,
            "reorder_after_outcome": False,
        },
        "tasks": list(TASKS),
        "operation_policy_ref": "agent-workflow-stage-b-calibration-v1",
        "runtime_candidate": {
            "orchestration_mode": "agent_workflow_node_v1",
            "protocol_path": PROTOCOL_PATH,
            "runner_path": RUNNER_PATH,
            "external_evaluator": "external-evaluator-v1",
            "clean_replay_required": True,
            "finalize_and_cleanup_required": True,
            "zero_managed_orphans_required": True,
        },
        "evidence_candidate": {
            "directory": EVIDENCE_DIRECTORY,
            "create_once": True,
            "historical_evidence_reused": False,
            "task_result_path": "tasks/{task_id}/result.json",
            "batch_marker": "markers/batch.json",
            "batch_report": "reports/stage-b-calibration.json",
            "writes_authorized": False,
        },
        "reporting": {
            "independent_layers": ["candidate_generated", "candidate_submitted", "s0_s5", "bitwise_reproducible"],
            "unbiased_success_rate_claim_allowed": False,
            "stage_c_authorized": False,
        },
        "frozen_components": _frozen_components(repo_root),
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-agent-workflow-stage-b-calibration-candidate.schema.json",
        "title": "Forge Agent Workflow Stage B calibration candidate",
        "const": manifest,
    }


def validate_manifest(value: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    expected = generate_manifest(repo_root)
    if value != expected:
        raise Phase5ProtocolError("Phase 5 candidate manifest 与确定性生成结果不一致")
    schema = generate_schema(expected)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(value, schema)
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase5ProtocolError("无法读取 Phase 5 candidate manifest") from exc
    if not isinstance(value, dict):
        raise Phase5ProtocolError("Phase 5 candidate manifest 必须是 JSON object")
    return validate_manifest(value, repo_root)


def collect_preflight(value: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    manifest = validate_manifest(value, repo_root)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, check=True, capture_output=True, text=True, timeout=30).stdout.strip()
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, revision], cwd=repo_root, check=False, capture_output=True, text=True, timeout=30)
    if ancestor.returncode != 0:
        raise Phase5ProtocolError("Phase 5 baseline commit 不是当前 release 的祖先")
    return {
        "status": "candidate_valid_not_authorized",
        "manifest_sha256": canonical_sha256(manifest),
        "release_revision": revision,
        "task_count": len(manifest["tasks"]),
        "build_system_counts": {name: sum(task["build_system"] == name for task in manifest["tasks"]) for name in ("cmake", "make", "autotools")},
        "historical_audit": manifest["historical_baseline"]["audit"],
        "provider_calls": 0,
        "credential_reads": 0,
        "docker_executions": 0,
        "formal_attempts": 0,
        "model_tokens": 0,
        "evidence_writes": 0,
    }


def write_artifacts(repo_root: Path = REPO_ROOT) -> None:
    manifest = generate_manifest(repo_root)
    schema = generate_schema(manifest)
    for path, value in ((repo_root / MANIFEST_RELATIVE_PATH, manifest), (repo_root / SCHEMA_RELATIVE_PATH, schema)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "validate", "audit", "preflight"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    if args.command == "generate":
        write_artifacts()
        result: Any = {"status": "generated", "manifest": MANIFEST_RELATIVE_PATH, "schema": SCHEMA_RELATIVE_PATH}
    else:
        manifest = load_manifest(args.manifest)
        if args.command == "validate":
            result = {"status": "valid", "manifest_sha256": canonical_sha256(manifest)}
        elif args.command == "audit":
            result = manifest["historical_baseline"]["audit"]
        else:
            result = collect_preflight(manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

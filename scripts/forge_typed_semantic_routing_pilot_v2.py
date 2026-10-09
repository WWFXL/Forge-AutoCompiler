#!/usr/bin/env python3
"""Issue #391 同阶段异根因语义路由 benchmark v2 零 Provider pilot。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
import tempfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import forge_typed_action_benchmark_qualification as v1
import jsonschema
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
IDENTITY = "cpp-typed-semantic-routing-pilot-v2"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/391"
SCHEMA_VERSION = "forge-typed-semantic-routing-pilot-2.0.0"
REPORT_SCHEMA_VERSION = "forge-typed-semantic-routing-pilot-report-2.0.0"

DEFAULT_SOURCE_POOL = (
    REPO_ROOT
    / "benchmarks/fixtures/cpp-typed-semantic-routing-pilot-v2-source-pool.json"
)
DEFAULT_MANIFEST = (
    REPO_ROOT / "benchmarks/manifests/cpp-typed-semantic-routing-pilot-v2.json"
)
DEFAULT_SCHEMA = (
    REPO_ROOT / "benchmarks/schemas/forge-typed-semantic-routing-pilot-v2.schema.json"
)
DEFAULT_JSON_REPORT = (
    REPO_ROOT / "benchmarks/reports/cpp-typed-semantic-routing-pilot-v2.json"
)
DEFAULT_MARKDOWN_REPORT = (
    REPO_ROOT / "benchmarks/reports/cpp-typed-semantic-routing-pilot-v2.md"
)
PREREGISTRATION = (
    REPO_ROOT / "benchmarks/preregistrations/cpp-typed-semantic-routing-pilot-v2.md"
)
V1_SOURCE_POOL = (
    REPO_ROOT / "benchmarks/fixtures/cpp-typed-action-benchmark-source-pool-v1.json"
)

BUILD_SYSTEMS = ("cmake", "make", "autotools")
FAULT_TYPES = ("missing_compile_input", "invalid_build_state", "wrong_build_target")
ACTION_FAMILIES = ("dependency", "configure", "build", "escalate_agent")
ACTION_COSTS = {"build": 1, "configure": 2, "dependency": 3, "escalate_agent": 4}
GATE_ORDER = (
    "expected_counts",
    "reference_closure",
    "replay_consistency",
    "all_build_systems_complete",
    "direct_actions_optimal_in_two_project_families",
    "rule_gate_top1_below_ceiling",
    "rule_gate_coverage_below_ceiling",
    "tfidf_top1_below_ceiling",
    "no_direct_label_leakage",
    "all_candidates_bounded",
)
EXPECTED_PHASE_FACTS = {
    "source_available": True,
    "configured": True,
    "build_attempted": True,
    "build_succeeded": False,
    "artifacts_staged": False,
    "functional_oracle_passed": False,
    "strict_verifier_passed": False,
}
OPAQUE_TARGET = "forge_probe_7b92e1"


class PilotError(RuntimeError):
    """Pilot 合同、环境或结果不满足冻结要求。"""


def _task(
    *,
    fault_file: str,
    configure_repair_commands: list[str],
    **kwargs: Any,
) -> dict[str, Any]:
    task = v1._task(**kwargs)
    task["project_family"] = v1.normalize_project_family(task["repository_url"])
    task["fault_file"] = fault_file
    task["configure_repair_commands"] = configure_repair_commands
    return task


TASKS = (
    _task(
        task_id="args",
        repository_url="https://github.com/Taywee/args",
        commit_sha="fe4450bd9549e4e02bc2047b2a2800b09f1bb878",
        commit_committed_at="2026-07-28T16:22:49-06:00",
        source_snapshot_sha256="b96e278749a1d9d311845a449cf354cdaa4aa799ab92f4e61f9aa4ba35bb0112",
        license_path="LICENSE",
        license_sha256="e434153d0eab720e3a4d2b6f7721e4168d6cade2ac940984705a6506208c1444",
        build_system="cmake",
        configure_commands=[
            "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DARGS_BUILD_EXAMPLE=ON "
            "-DARGS_BUILD_UNITTESTS=OFF -DBUILD_FUZZERS=OFF"
        ],
        build_commands=["cmake --build build --target gitlike --parallel 4"],
        artifact_stage_commands=["cp build/gitlike /artifacts/gitlike"],
        required_artifacts=["gitlike"],
        artifact_types=["executable"],
        oracle={"kind": "command", "argv": ["/artifacts/gitlike", "--help"]},
        tracked_file_count=132,
        fault_file="args.hxx",
        configure_repair_commands=[
            "rm -rf build",
            "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DARGS_BUILD_EXAMPLE=ON "
            "-DARGS_BUILD_UNITTESTS=OFF -DBUILD_FUZZERS=OFF",
        ],
    ),
    _task(
        task_id="yyjson",
        repository_url="https://github.com/ibireme/yyjson",
        commit_sha="9365ddc7061033df656578bf86040048b5b5531a",
        commit_committed_at="2026-07-23T01:31:33+08:00",
        source_snapshot_sha256="b13682f846a765bded86bac6baf23645771288605974dfdb66f1d4c66ac48465",
        license_path="LICENSE",
        license_sha256="45e384d3d52c73cba3a64d6e6c25d47cd738cd8a55c30629e3201046eda62947",
        build_system="cmake",
        configure_commands=[
            "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF "
            "-DYYJSON_BUILD_TESTS=OFF -DYYJSON_BUILD_FUZZER=OFF"
        ],
        build_commands=["cmake --build build --target yyjson --parallel 4"],
        artifact_stage_commands=[
            "mkdir -p /artifacts/lib /artifacts/include && cp build/libyyjson.a "
            "/artifacts/lib/libyyjson.a && cp src/yyjson.h /artifacts/include/yyjson.h"
        ],
        required_artifacts=["include/yyjson.h", "lib/libyyjson.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": '#include <yyjson.h>\nint main(void){ yyjson_doc *d=yyjson_read("null",4,0); if(!d) return 1; yyjson_doc_free(d); return 0; }\n',
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libyyjson.a",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=911,
        fault_file="src/yyjson.c",
        configure_repair_commands=[
            "rm -rf build",
            "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF "
            "-DYYJSON_BUILD_TESTS=OFF -DYYJSON_BUILD_FUZZER=OFF",
        ],
    ),
    _task(
        task_id="hoextdown",
        repository_url="https://github.com/kjdev/hoextdown",
        commit_sha="1ef9a71957570c2a65b7daa1b2f693ad87daf385",
        commit_committed_at="2026-05-14T12:27:58+09:00",
        source_snapshot_sha256="0a230ee9c50eaa10dc0b97233c91500621087fff6bb70deb50aff4a3c2ec0234",
        license_path="LICENSE",
        license_sha256="d69aaff1b278160affc7e73bbab8c40e51e25d3d9a61cff5c3b20629e2cedce4",
        build_system="make",
        configure_commands=["test -f Makefile"],
        build_commands=["make -j4 libhoedown.a"],
        artifact_stage_commands=[
            "mkdir -p /artifacts/lib /artifacts/include && cp libhoedown.a "
            "/artifacts/lib/libhoedown.a && cp src/*.h /artifacts/include/"
        ],
        required_artifacts=["include/buffer.h", "lib/libhoedown.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <buffer.h>\nint main(void){ hoedown_buffer *b=hoedown_buffer_new(8); if(!b) return 1; hoedown_buffer_free(b); return 0; }\n",
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libhoedown.a",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=210,
        fault_file="src/buffer.c",
        configure_repair_commands=["git checkout HEAD -- Makefile", "test -f Makefile"],
    ),
    _task(
        task_id="hiredis",
        repository_url="https://github.com/redis/hiredis",
        commit_sha="60e5075d4ac77424809f855ba3e398df7aacefe8",
        commit_committed_at="2023-07-12T10:31:17+03:00",
        source_snapshot_sha256="9dbac5f1b829453675b212432d696ab67a928ef2aa4657dc26edbb50d1395cba",
        license_path="COPYING",
        license_sha256="dca05ce8fc87a8261783b4aed0deef8becc9350b6aa770bc714d0c1833b896eb",
        build_system="make",
        configure_commands=["test -f Makefile"],
        build_commands=["make -j4 static"],
        artifact_stage_commands=[
            "mkdir -p /artifacts/lib /artifacts/include/hiredis && cp libhiredis.a "
            "/artifacts/lib/libhiredis.a && cp *.h /artifacts/include/hiredis/"
        ],
        required_artifacts=["include/hiredis/hiredis.h", "lib/libhiredis.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <hiredis/read.h>\nint main(void){ redisReader *r=redisReaderCreateWithFunctions(0); if(!r) return 1; redisReaderFree(r); return 0; }\n",
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libhiredis.a",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=72,
        fault_file="hiredis.c",
        configure_repair_commands=["git checkout HEAD -- Makefile", "test -f Makefile"],
    ),
    _task(
        task_id="c-ares",
        repository_url="https://github.com/c-ares/c-ares",
        commit_sha="589b5887d47736e5b70a1fddaf9bf90297adde65",
        commit_committed_at="2026-07-12T13:44:45+00:00",
        source_snapshot_sha256="b681abdf95bac81e4c1ea1df5415e63072b034dda804ecbc89c84cb349de26a9",
        license_path="LICENSE.md",
        license_sha256="460f5e768fda3752ca2169a95df062578a10fb126bfd65f3b9b1a1bed2f84807",
        build_system="autotools",
        configure_commands=[
            "autoreconf -fi",
            "./configure --prefix=/artifacts --disable-shared --enable-static --disable-tests",
        ],
        build_commands=["make -j4"],
        artifact_stage_commands=["make install"],
        required_artifacts=["include/ares.h", "lib/libcares.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <ares.h>\nint main(void){ if(ares_library_init(ARES_LIB_INIT_ALL)!=ARES_SUCCESS) return 1; ares_library_cleanup(); return 0; }\n",
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libcares.a",
                "-pthread",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=574,
        fault_file="src/lib/ares_library_init.c",
        configure_repair_commands=[
            "autoreconf -fi",
            "./configure --prefix=/artifacts --disable-shared --enable-static --disable-tests",
        ],
    ),
    _task(
        task_id="numactl",
        repository_url="https://github.com/numactl/numactl",
        commit_sha="93c1fe5fabf38502ca315598bf74699c41300df9",
        commit_committed_at="2026-06-30T15:56:45-07:00",
        source_snapshot_sha256="647886e65bfa5c33dc1ed199fd512530957049e93aa8c954d354d8d3b6b19fa8",
        license_path="LICENSE.GPL2",
        license_sha256="ab15fd526bd8dd18a9e77ebc139656bf4d33e97fc7238cd11bf60e2b9b8666c6",
        build_system="autotools",
        configure_commands=[
            "./autogen.sh",
            "./configure --prefix=/artifacts --disable-shared --enable-static",
        ],
        build_commands=["make -j4 libnuma.la"],
        artifact_stage_commands=["make install"],
        required_artifacts=["include/numa.h", "lib/libnuma.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <numa.h>\nint main(void){ volatile int r=numa_available(); return r < -1; }\n",
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libnuma.a",
                "-ldl",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=91,
        fault_file="libnuma.c",
        configure_repair_commands=[
            "./autogen.sh",
            "./configure --prefix=/artifacts --disable-shared --enable-static",
        ],
    ),
)


def generate_source_pool() -> dict[str, Any]:
    return {
        "schema_version": "forge-typed-semantic-routing-source-pool-2.0.0",
        "identity": IDENTITY,
        "selection_status": "frozen_before_outcomes",
        "quotas": {"project_count": 6, "projects_per_build_system": 2},
        "selection_audit": {
            "included_project_ids": [task["task_id"] for task in TASKS],
            "excluded_before_freeze": [
                {
                    "task_id": "libcheck",
                    "reason": "fixed_image_missing_makeinfo",
                    "outcome_matrix_observed": False,
                },
                {
                    "task_id": "jpegoptim",
                    "reason": "fixed_image_missing_libjpeg_dev",
                    "outcome_matrix_observed": False,
                },
                {
                    "task_id": "libusb",
                    "reason": "git_archive_clean_replay_version_string_is_not_bitwise_stable",
                    "outcome_matrix_observed": False,
                },
            ],
        },
        "tasks": list(TASKS),
    }


def generate_manifest(source_pool: dict[str, Any] | None = None) -> dict[str, Any]:
    pool = source_pool or generate_source_pool()
    return {
        "$schema": "../schemas/forge-typed-semantic-routing-pilot-v2.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": "forge_typed_semantic_routing_pilot",
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "status": "authorized_zero_provider_pilot",
        "authorization": {
            "provider_calls_authorized": False,
            "credential_read_authorized": False,
            "model_calls_authorized": False,
            "model_tokens_authorized": 0,
            "controller_implementation_authorized": False,
            "docker_action_execution_authorized": True,
            "new_identity_evidence_write_authorized": True,
            "historical_evidence_write_authorized": False,
        },
        "source_pool": {
            "path": DEFAULT_SOURCE_POOL.relative_to(REPO_ROOT).as_posix(),
            "canonical_sha256": v1.canonical_sha256(pool),
            "task_ids": [task["task_id"] for task in pool["tasks"]],
        },
        "environment": {
            "dockerfile_path": "docker/compile/Dockerfile.stage-c",
            "image_tag": "autocompiler:stage-c-v1",
            "expected_image_id": "sha256:adbef4a26de49e9cd2c361a50b5fe2a000073a343b072ed0e515cc67e6e758b1",
            "network_during_clone": True,
            "network_during_action": False,
            "parallel_jobs": 4,
            "per_action_timeout_seconds": 900,
            "replicates": 2,
        },
        "benchmark_design": {
            "project_count": 6,
            "projects_per_build_system": 2,
            "faults_per_project": 3,
            "fault_types": list(FAULT_TYPES),
            "actions_per_state": 4,
            "action_order": list(ACTION_FAMILIES),
            "action_costs": ACTION_COSTS,
            "phase_facts": EXPECTED_PHASE_FACTS,
            "state_id": "opaque_sha256_prefix",
            "hidden_fault_mapping_separate_from_model_input": True,
            "label_rule": "strict_success_then_minimum_frozen_action_cost",
            "continuation": [
                "normal_build",
                "artifact_stage",
                "functional_oracle",
                "exact_commit_provenance",
                "clean_replay",
            ],
            "old_agent_action_is_ground_truth": False,
            "shell_generation_by_model": False,
            "escalate_agent_execution": "zero_provider_deterministic_recovery_surrogate",
        },
        "baselines": {
            "rule_gate": {
                "inputs": ["phase_facts", "candidate_action_families", "action_costs"],
                "fixed_choice": "build",
            },
            "tfidf_logistic_regression": {
                "input": "semantic_failure_log_only",
                "split": "leave_one_project_family_out",
                "ngram_range": [1, 2],
                "sublinear_tf": True,
                "max_features": 5000,
                "solver": "liblinear",
                "multiclass_strategy": "one_vs_rest",
                "c": 1.0,
                "random_state": 391,
            },
        },
        "qualification_thresholds": {
            "minimum_replay_consistency": 0.95,
            "minimum_project_families_per_direct_optimal_action": 2,
            "maximum_rule_gate_top1_exclusive": 0.75,
            "maximum_rule_gate_route_acceptable_coverage_exclusive": 0.90,
            "maximum_tfidf_top1_exclusive": 0.95,
            "require_all_build_systems_complete": True,
            "require_no_direct_label_leakage": True,
        },
        "decision_rule": {
            "pass": "proceed_to_jev_offline_qualification",
            "fail": "stop_jev_provider_qualification",
            "threshold_adjustment_after_results": False,
            "project_replacement_after_results": False,
        },
        "preregistration": {
            "path": PREREGISTRATION.relative_to(REPO_ROOT).as_posix(),
            "must_be_committed_and_pushed_before_outcomes": True,
        },
        "outputs": {
            "json_report": DEFAULT_JSON_REPORT.relative_to(REPO_ROOT).as_posix(),
            "markdown_report": DEFAULT_MARKDOWN_REPORT.relative_to(
                REPO_ROOT
            ).as_posix(),
        },
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-typed-semantic-routing-pilot-v2.schema.json",
        "title": "Forge typed semantic routing pilot v2",
        "const": manifest,
    }


def _safe_relative(value: str) -> None:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise PilotError(f"不安全的相对路径: {value}")


def validate_source_pool(pool: dict[str, Any]) -> dict[str, Any]:
    if (
        pool.get("schema_version") != "forge-typed-semantic-routing-source-pool-2.0.0"
        or pool.get("identity") != IDENTITY
    ):
        raise PilotError("source pool identity 无效")
    tasks = pool.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 6:
        raise PilotError("source pool 必须包含 6 个项目")
    if Counter(task.get("selected_build_system") for task in tasks) != {
        name: 2 for name in BUILD_SYSTEMS
    }:
        raise PilotError("构建系统配额漂移")
    ids = [task.get("task_id") for task in tasks]
    families = [task.get("project_family") for task in tasks]
    if len(set(ids)) != 6 or len(set(families)) != 6:
        raise PilotError("项目 identity 未隔离")
    v1_ids = {task["task_id"] for task in v1.load_json(V1_SOURCE_POOL)["tasks"]}
    if set(ids) & v1_ids:
        raise PilotError("v2 项目与已暴露的 v1 项目重叠")
    for task in tasks:
        if task["project_family"] != v1.normalize_project_family(
            task["repository_url"]
        ):
            raise PilotError(f"{task['task_id']} project family 漂移")
        if v1.HEX40.fullmatch(task["commit_sha"]) is None:
            raise PilotError(f"{task['task_id']} exact commit 无效")
        for name in ("source_snapshot_sha256", "license_sha256"):
            if v1.HEX64.fullmatch(task[name]) is None:
                raise PilotError(f"{task['task_id']} {name} 无效")
        for path in (
            task["license_path"],
            task["fault_file"],
            *task["target"]["required_artifacts"],
        ):
            _safe_relative(path)
        if (
            not task["configure_commands"]
            or not task["configure_repair_commands"]
            or not task["build_commands"]
        ):
            raise PilotError(f"{task['task_id']} 缺少冻结动作")
        commands = [
            *task["configure_commands"],
            *task["configure_repair_commands"],
            *task["build_commands"],
            *task["artifact_stage_commands"],
        ]
        forbidden = ("curl ", "wget ", "git clone", "git fetch", "apt-get", "sudo ")
        if any(token in command for command in commands for token in forbidden):
            raise PilotError(f"{task['task_id']} 动作包含网络或提权命令")
    exclusions = {
        item["task_id"]: item
        for item in pool["selection_audit"]["excluded_before_freeze"]
    }
    if set(exclusions) != {"libcheck", "jpegoptim", "libusb"} or any(
        item["outcome_matrix_observed"] for item in exclusions.values()
    ):
        raise PilotError("selection audit 漂移")
    return pool


def validate_manifest(
    manifest: dict[str, Any], pool: dict[str, Any], *, check_schema: bool = True
) -> dict[str, Any]:
    validate_source_pool(pool)
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("identity") != IDENTITY
    ):
        raise PilotError("manifest identity 无效")
    authorization = manifest.get("authorization", {})
    for key in (
        "provider_calls_authorized",
        "credential_read_authorized",
        "model_calls_authorized",
        "controller_implementation_authorized",
        "historical_evidence_write_authorized",
    ):
        if authorization.get(key) is not False:
            raise PilotError(f"manifest 意外授权 {key}")
    if (
        authorization.get("model_tokens_authorized") != 0
        or authorization.get("new_identity_evidence_write_authorized") is not True
    ):
        raise PilotError("零 Provider 或新 identity 写入边界无效")
    if manifest["source_pool"]["canonical_sha256"] != v1.canonical_sha256(pool):
        raise PilotError("source pool hash 漂移")
    design = manifest["benchmark_design"]
    if (
        tuple(design["fault_types"]) != FAULT_TYPES
        or tuple(design["action_order"]) != ACTION_FAMILIES
    ):
        raise PilotError("故障或动作目录漂移")
    if (
        design["phase_facts"] != EXPECTED_PHASE_FACTS
        or design["action_costs"] != ACTION_COSTS
    ):
        raise PilotError("统一阶段事实或冻结动作成本漂移")
    if check_schema:
        schema = v1.load_json(DEFAULT_SCHEMA)
        if schema != generate_schema(manifest):
            raise PilotError("const Schema 漂移")
        jsonschema.validate(manifest, schema)
    return manifest


def generate_contract_files() -> None:
    pool = generate_source_pool()
    manifest = generate_manifest(pool)
    schema = generate_schema(manifest)
    jsonschema.Draft202012Validator.check_schema(schema)
    v1.write_json(DEFAULT_SOURCE_POOL, pool)
    v1.write_json(DEFAULT_MANIFEST, manifest)
    v1.write_json(DEFAULT_SCHEMA, schema)


def load_contract() -> tuple[dict[str, Any], dict[str, Any]]:
    pool = validate_source_pool(v1.load_json(DEFAULT_SOURCE_POOL))
    manifest = validate_manifest(v1.load_json(DEFAULT_MANIFEST), pool)
    return manifest, pool


def _git_output(*argv: str) -> str:
    return v1._run_checked(["git", *argv])


def preflight(
    manifest: dict[str, Any], pool: dict[str, Any], *, require_clean: bool = True
) -> dict[str, Any]:
    v1.require_zero_managed_resources()
    image_id = v1.current_image_id(manifest)
    status = _git_output("status", "--porcelain")
    if require_clean and status:
        raise PilotError("正式 outcome 前工作树必须干净")
    branch = _git_output("branch", "--show-current")
    if branch != "yiwei/391-semantic-routing-pilot":
        raise PilotError(f"正式 outcome 分支漂移: {branch}")
    if not PREREGISTRATION.is_file():
        raise PilotError("缺少预注册")
    if DEFAULT_JSON_REPORT.exists() or DEFAULT_MARKDOWN_REPORT.exists():
        raise PilotError("pilot 报告已存在，禁止覆盖或续跑")
    return {
        "ready": True,
        "identity": IDENTITY,
        "task_count": len(pool["tasks"]),
        "expected_state_count": 18,
        "expected_action_branch_count": 144,
        "git_branch": branch,
        "git_commit": _git_output("rev-parse", "HEAD"),
        "image_id": image_id,
        "provider_calls": 0,
        "credential_reads": 0,
        "model_calls": 0,
        "model_tokens": 0,
    }


def _state_id(task: dict[str, Any], fault_type: str) -> str:
    digest = hashlib.sha256(
        f"{IDENTITY}|{task['project_family']}|{fault_type}".encode()
    ).hexdigest()
    return f"s-{digest[:20]}"


def _dependency_commands(task: dict[str, Any]) -> list[str]:
    return [f"git checkout HEAD -- {shlex.quote(task['fault_file'])}"]


def _action_commands(task: dict[str, Any], family: str) -> list[str]:
    if family == "dependency":
        return _dependency_commands(task)
    if family == "configure":
        return list(task["configure_repair_commands"])
    if family == "build":
        return list(task["build_commands"])
    if family == "escalate_agent":
        return [*_dependency_commands(task), *task["configure_repair_commands"]]
    raise PilotError(f"未知 action family: {family}")


def _action_contract(
    task: dict[str, Any], state_id: str, family: str
) -> dict[str, Any]:
    return {
        "action_id": f"{state_id}:{family}",
        "action_family": family,
        "executor": "zero_provider_recovery_surrogate"
        if family == "escalate_agent"
        else "docker_command",
        "bound_commands": _action_commands(task, family),
        "cost": ACTION_COSTS[family],
        "direct_execution": family != "escalate_agent",
        "preconditions_checked_by_runner": True,
    }


def _state_record(
    task: dict[str, Any], fault_type: str, semantic_log: str
) -> dict[str, Any]:
    state_id = _state_id(task, fault_type)
    candidate_actions = [
        _action_contract(task, state_id, family) for family in ACTION_FAMILIES
    ]
    model_input = {
        "state_id": state_id,
        "build_system": task["selected_build_system"],
        "phase_facts": EXPECTED_PHASE_FACTS,
        "semantic_failure_log": semantic_log,
        "candidate_action_families": list(ACTION_FAMILIES),
        "remaining_budget": {"actions": 8, "wall_clock_seconds": 900},
    }
    return {
        "state_id": state_id,
        "project_id": task["task_id"],
        "project_family": task["project_family"],
        "build_system": task["selected_build_system"],
        "phase_facts": EXPECTED_PHASE_FACTS,
        "semantic_failure_log": semantic_log,
        "candidate_actions": candidate_actions,
        "model_input": model_input,
    }


def _fault_trigger_command(task: dict[str, Any], fault_type: str) -> str:
    if fault_type == "missing_compile_input":
        return v1._commands_script(
            [f"rm -f {shlex.quote(task['fault_file'])}", *task["build_commands"]]
        )
    if fault_type == "invalid_build_state":
        invalid_path = (
            "build/Makefile" if task["selected_build_system"] == "cmake" else "Makefile"
        )
        return v1._commands_script(
            [
                f"printf '%s\\n' all > {shlex.quote(invalid_path)}",
                *task["build_commands"],
            ]
        )
    if fault_type == "wrong_build_target":
        if task["selected_build_system"] == "cmake":
            return f"cmake --build build --target {OPAQUE_TARGET} --parallel 4"
        return f"make {OPAQUE_TARGET}"
    raise PilotError(f"未知 fault type: {fault_type}")


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, symlinks=True)


def _reference_closure(
    *,
    manifest: dict[str, Any],
    image: str,
    task: dict[str, Any],
    configured_workspace: Path,
    replicate: int,
    root: Path,
) -> dict[str, Any]:
    workspace = root / "workspace"
    artifacts = root / "artifacts"
    _copy_tree(configured_workspace, workspace)
    artifacts.mkdir(parents=True)
    execution = v1._run_container(
        manifest=manifest,
        image=image,
        workspace=workspace,
        artifacts=artifacts,
        script=v1._commands_script(
            [
                *task["build_commands"],
                *task["artifact_stage_commands"],
                v1._oracle_script(task, f"reference-{replicate}"),
            ]
        ),
        log_path=root / "reference.log",
    )
    if execution["exit_code"] != 0 or execution["timed_out"]:
        raise PilotError(
            f"{task['task_id']} reference closure 失败: {execution['log_tail']}"
        )
    artifacts_evidence = v1._artifact_evidence(task, artifacts)
    strict_root = root / "strict"
    strict_root.mkdir()
    strict = v1._strict_submit(
        manifest=manifest,
        image=image,
        task=task,
        workspace=workspace,
        artifacts=artifacts,
        root=strict_root,
        log_path=strict_root / "strict.log",
    )
    if strict["exit_code"] != 0 or strict["timed_out"]:
        raise PilotError(
            f"{task['task_id']} strict reference closure 失败: {strict['log_tail']}"
        )
    return {
        "task_id": task["task_id"],
        "replicate": replicate,
        "reference_passed": True,
        "reference_log_sha256": execution["log_sha256"],
        "strict_checks": strict["strict_checks"],
        "artifacts": artifacts_evidence,
    }


def _inject_fault(
    *,
    manifest: dict[str, Any],
    image: str,
    task: dict[str, Any],
    fault_type: str,
    workspace: Path,
    artifacts: Path,
    log_path: Path,
) -> dict[str, Any]:
    result = v1._run_container(
        manifest=manifest,
        image=image,
        workspace=workspace,
        artifacts=artifacts,
        script=_fault_trigger_command(task, fault_type),
        log_path=log_path,
    )
    if result["exit_code"] in (None, 0) or result["timed_out"]:
        raise PilotError(f"{task['task_id']} {fault_type} 未形成有界构建失败")
    return result


def _execute_action_branch(
    *,
    manifest: dict[str, Any],
    image: str,
    task: dict[str, Any],
    state: dict[str, Any],
    action: dict[str, Any],
    fault_workspace: Path,
    replicate: int,
    root: Path,
) -> dict[str, Any]:
    workspace = root / "workspace"
    artifacts = root / "artifacts"
    _copy_tree(fault_workspace, workspace)
    artifacts.mkdir()
    action_result = v1._run_container(
        manifest=manifest,
        image=image,
        workspace=workspace,
        artifacts=artifacts,
        script=v1._commands_script(action["bound_commands"]),
        log_path=root / "action.log",
    )
    action_succeeded = (
        action_result["exit_code"] == 0 and not action_result["timed_out"]
    )
    continuation: dict[str, Any] | None = None
    strict: dict[str, Any] | None = None
    if action_succeeded:
        continuation = v1._run_container(
            manifest=manifest,
            image=image,
            workspace=workspace,
            artifacts=artifacts,
            script=v1._commands_script(
                [
                    *task["build_commands"],
                    *task["artifact_stage_commands"],
                    v1._oracle_script(
                        task, f"continuation-{state['state_id']}-{replicate}"
                    ),
                ]
            ),
            log_path=root / "continuation.log",
        )
        continuation_succeeded = (
            continuation["exit_code"] == 0 and not continuation["timed_out"]
        )
        if continuation_succeeded:
            strict_root = root / "strict"
            strict_root.mkdir()
            strict = v1._strict_submit(
                manifest=manifest,
                image=image,
                task=task,
                workspace=workspace,
                artifacts=artifacts,
                root=strict_root,
                log_path=strict_root / "strict.log",
            )
    continuation_succeeded = bool(
        continuation is not None
        and continuation["exit_code"] == 0
        and not continuation["timed_out"]
    )
    strict_success = bool(
        strict is not None
        and strict["exit_code"] == 0
        and not strict["timed_out"]
        and all(
            strict.get("strict_checks", {}).get(name) is True
            for name in ("candidate", "functional", "provenance", "clean_replay")
        )
    )
    signature = {
        "action_family": action["action_family"],
        "action_exit_class": "timeout"
        if action_result["timed_out"]
        else "success"
        if action_result["exit_code"] == 0
        else "failure",
        "continuation_exit_class": "not_run"
        if continuation is None
        else "timeout"
        if continuation["timed_out"]
        else "success"
        if continuation["exit_code"] == 0
        else "failure",
        "strict_success": strict_success,
    }
    return {
        "state_id": state["state_id"],
        "project_id": task["task_id"],
        "project_family": task["project_family"],
        "build_system": task["selected_build_system"],
        "replicate": replicate,
        "action_id": action["action_id"],
        "action_family": action["action_family"],
        "action_cost": action["cost"],
        "direct_execution": action["direct_execution"],
        "action_exit_code": action_result["exit_code"],
        "action_timed_out": action_result["timed_out"],
        "action_duration_seconds": action_result["duration_seconds"],
        "action_log_sha256": action_result["log_sha256"],
        "action_log_tail": action_result["log_tail"],
        "continuation_exit_code": None
        if continuation is None
        else continuation["exit_code"],
        "continuation_timed_out": None
        if continuation is None
        else continuation["timed_out"],
        "continuation_duration_seconds": None
        if continuation is None
        else continuation["duration_seconds"],
        "continuation_log_sha256": None
        if continuation is None
        else continuation["log_sha256"],
        "continuation_log_tail": None
        if continuation is None
        else continuation["log_tail"],
        "strict_checks": None if strict is None else strict["strict_checks"],
        "strict_exit_code": None if strict is None else strict["exit_code"],
        "strict_timed_out": None if strict is None else strict["timed_out"],
        "strict_success": strict_success,
        "route_acceptable": strict_success
        or action["action_family"] == "escalate_agent",
        "replay_signature": signature,
    }


def _run_project_replicate(
    *,
    manifest: dict[str, Any],
    image: str,
    task: dict[str, Any],
    replicate: int,
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], dict[str, str]]:
    source = root / "source"
    configured_workspace = root / "configured"
    empty_artifacts = root / "configured-artifacts"
    v1._clone_exact(task, source)
    source_identity = v1._verify_source(task, source)
    _copy_tree(source, configured_workspace)
    empty_artifacts.mkdir()
    configured = v1._run_container(
        manifest=manifest,
        image=image,
        workspace=configured_workspace,
        artifacts=empty_artifacts,
        script=v1._commands_script(task["configure_commands"]),
        log_path=root / "configure.log",
    )
    if configured["exit_code"] != 0 or configured["timed_out"]:
        raise PilotError(
            f"{task['task_id']} configure checkpoint 失败: {configured['log_tail']}"
        )
    reference_root = root / "reference"
    reference_root.mkdir()
    closure = _reference_closure(
        manifest=manifest,
        image=image,
        task=task,
        configured_workspace=configured_workspace,
        replicate=replicate,
        root=reference_root,
    )
    closure["source_identity"] = source_identity

    states: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    hidden_mapping: dict[str, str] = {}
    for fault_type in FAULT_TYPES:
        fault_root = root / f"fault-{FAULT_TYPES.index(fault_type) + 1}"
        fault_workspace = fault_root / "workspace"
        fault_artifacts = fault_root / "artifacts"
        fault_root.mkdir()
        _copy_tree(configured_workspace, fault_workspace)
        fault_artifacts.mkdir()
        fault_result = _inject_fault(
            manifest=manifest,
            image=image,
            task=task,
            fault_type=fault_type,
            workspace=fault_workspace,
            artifacts=fault_artifacts,
            log_path=fault_root / "fault.log",
        )
        state = _state_record(task, fault_type, fault_result["log_tail"])
        hidden_mapping[state["state_id"]] = fault_type
        states.append(state)
        for action in state["candidate_actions"]:
            action_root = fault_root / f"action-{action['action_family']}"
            action_root.mkdir()
            outcome = _execute_action_branch(
                manifest=manifest,
                image=image,
                task=task,
                state=state,
                action=action,
                fault_workspace=fault_workspace,
                replicate=replicate,
                root=action_root,
            )
            outcome["fault_trigger_exit_code"] = fault_result["exit_code"]
            outcome["fault_trigger_log_sha256"] = fault_result["log_sha256"]
            outcomes.append(outcome)
    return states, outcomes, closure, hidden_mapping


def _derive_labels(
    states: list[dict[str, Any]], outcomes: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for outcome in outcomes:
        grouped[(outcome["state_id"], outcome["action_family"])].append(outcome)
    labels: list[dict[str, Any]] = []
    consistent_pairs = 0
    for state in states:
        successful: list[str] = []
        for family in ACTION_FAMILIES:
            rows = sorted(
                grouped[(state["state_id"], family)], key=lambda item: item["replicate"]
            )
            if len(rows) != 2:
                raise PilotError(f"{state['state_id']} {family} 缺少两次 replay")
            if rows[0]["replay_signature"] == rows[1]["replay_signature"]:
                consistent_pairs += 1
            if all(row["strict_success"] for row in rows):
                successful.append(family)
        if not successful:
            raise PilotError(f"{state['state_id']} 没有达到严格终点的动作")
        minimum_cost = min(ACTION_COSTS[family] for family in successful)
        optimal = [
            family for family in successful if ACTION_COSTS[family] == minimum_cost
        ]
        if len(optimal) != 1:
            raise PilotError(f"{state['state_id']} 最优动作不唯一")
        labels.append(
            {
                "state_id": state["state_id"],
                "project_id": state["project_id"],
                "project_family": state["project_family"],
                "build_system": state["build_system"],
                "successful_actions": successful,
                "optimal_action": optimal[0],
                "optimal_cost": minimum_cost,
            }
        )
    pair_count = len(states) * len(ACTION_FAMILIES)
    consistency = consistent_pairs / pair_count if pair_count else 0.0
    return labels, {
        "state_action_pair_count": pair_count,
        "consistent_state_action_pair_count": consistent_pairs,
        "replay_consistency": round(consistency, 6),
    }


def _rule_gate(
    states: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    labels_by_state = {row["state_id"]: row["optimal_action"] for row in labels}
    outcome_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for outcome in outcomes:
        outcome_groups[(outcome["state_id"], outcome["action_family"])].append(outcome)
    successful = {
        key
        for key, rows_for_action in outcome_groups.items()
        if len(rows_for_action) == 2
        and all(row["strict_success"] for row in rows_for_action)
    }
    rows: list[dict[str, Any]] = []
    for state in states:
        prediction = "build"
        state_id = state["state_id"]
        acceptable = (state_id, prediction) in successful
        rows.append(
            {
                "state_id": state_id,
                "project_family": state["project_family"],
                "build_system": state["build_system"],
                "prediction": prediction,
                "optimal_action": labels_by_state[state_id],
                "top1_correct": prediction == labels_by_state[state_id],
                "route_acceptable": acceptable,
            }
        )
    return {
        "state_count": len(rows),
        "top1_correct": sum(row["top1_correct"] for row in rows),
        "top1_accuracy": round(sum(row["top1_correct"] for row in rows) / len(rows), 6),
        "route_acceptable_count": sum(row["route_acceptable"] for row in rows),
        "route_acceptable_coverage": round(
            sum(row["route_acceptable"] for row in rows) / len(rows), 6
        ),
        "rows": rows,
    }


def _tfidf_baseline(
    states: list[dict[str, Any]], labels: list[dict[str, Any]]
) -> dict[str, Any]:
    labels_by_state = {row["state_id"]: row["optimal_action"] for row in labels}
    rows: list[dict[str, Any]] = []
    families = sorted({state["project_family"] for state in states})
    for held_out in families:
        train = [state for state in states if state["project_family"] != held_out]
        test = [state for state in states if state["project_family"] == held_out]
        vectorizer = TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),
            sublinear_tf=True,
            max_features=5000,
        )
        x_train = vectorizer.fit_transform(
            state["semantic_failure_log"] for state in train
        )
        x_test = vectorizer.transform(state["semantic_failure_log"] for state in test)
        y_train = [labels_by_state[state["state_id"]] for state in train]
        classifier = OneVsRestClassifier(
            LogisticRegression(
                C=1.0,
                solver="liblinear",
                random_state=391,
                max_iter=1000,
            )
        )
        classifier.fit(x_train, y_train)
        predictions = classifier.predict(x_test)
        for state, prediction in zip(test, predictions, strict=True):
            expected = labels_by_state[state["state_id"]]
            rows.append(
                {
                    "state_id": state["state_id"],
                    "held_out_project_family": held_out,
                    "build_system": state["build_system"],
                    "prediction": str(prediction),
                    "optimal_action": expected,
                    "top1_correct": str(prediction) == expected,
                }
            )
    rows.sort(key=lambda item: item["state_id"])
    correct = sum(row["top1_correct"] for row in rows)
    return {
        "state_count": len(rows),
        "top1_correct": correct,
        "top1_accuracy": round(correct / len(rows), 6),
        "rows": rows,
    }


def _leakage_audit(states: list[dict[str, Any]]) -> dict[str, Any]:
    forbidden = set(FAULT_TYPES)
    violations: list[dict[str, str]] = []
    for state in states:
        payload = json.dumps(
            state["model_input"], ensure_ascii=False, sort_keys=True
        ).lower()
        state_id = state["state_id"].lower()
        commands = json.dumps(
            [action["bound_commands"] for action in state["candidate_actions"]],
            ensure_ascii=False,
            sort_keys=True,
        ).lower()
        for token in forbidden:
            if token in payload or token in state_id or token in commands:
                violations.append({"state_id": state["state_id"], "token": token})
    same_commands_within_project = all(
        len(
            {
                v1.canonical_sha256(
                    [action["bound_commands"] for action in state["candidate_actions"]]
                )
                for state in states
                if state["project_family"] == project_family
            }
        )
        == 1
        for project_family in {state["project_family"] for state in states}
    )
    return {
        "passed": not violations and same_commands_within_project,
        "violations": violations,
        "same_candidate_order_all_states": all(
            [action["action_family"] for action in state["candidate_actions"]]
            == list(ACTION_FAMILIES)
            for state in states
        ),
        "same_bound_commands_within_project": same_commands_within_project,
        "hidden_fault_field_in_model_input": False,
    }


def analyse_results(
    manifest: dict[str, Any],
    states: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    reference_closures: list[dict[str, Any]],
) -> dict[str, Any]:
    labels, replay = _derive_labels(states, outcomes)
    rule_gate = _rule_gate(states, labels, outcomes)
    tfidf = _tfidf_baseline(states, labels)
    leakage = _leakage_audit(states)
    optimal_projects: dict[str, set[str]] = defaultdict(set)
    for label in labels:
        optimal_projects[label["optimal_action"]].add(label["project_family"])
    labels_by_state = {row["state_id"]: row for row in labels}
    systems_complete = all(
        len(
            system_states := [
                state for state in states if state["build_system"] == build_system
            ]
        )
        == 6
        and {
            labels_by_state[state["state_id"]]["optimal_action"]
            for state in system_states
        }
        == {"dependency", "configure", "build"}
        for build_system in BUILD_SYSTEMS
    )
    thresholds = manifest["qualification_thresholds"]
    gates = {
        "expected_counts": len(states) == 18
        and len(outcomes) == 144
        and len(reference_closures) == 12,
        "reference_closure": all(
            row["reference_passed"] and all(row["strict_checks"].values())
            for row in reference_closures
        ),
        "replay_consistency": replay["replay_consistency"]
        >= thresholds["minimum_replay_consistency"],
        "all_build_systems_complete": systems_complete,
        "direct_actions_optimal_in_two_project_families": all(
            len(optimal_projects[family])
            >= thresholds["minimum_project_families_per_direct_optimal_action"]
            for family in ("dependency", "configure", "build")
        ),
        "rule_gate_top1_below_ceiling": rule_gate["top1_accuracy"]
        < thresholds["maximum_rule_gate_top1_exclusive"],
        "rule_gate_coverage_below_ceiling": rule_gate["route_acceptable_coverage"]
        < thresholds["maximum_rule_gate_route_acceptable_coverage_exclusive"],
        "tfidf_top1_below_ceiling": tfidf["top1_accuracy"]
        < thresholds["maximum_tfidf_top1_exclusive"],
        "no_direct_label_leakage": leakage["passed"],
        "all_candidates_bounded": all(
            row["action_timed_out"] is False
            and row["action_exit_code"] is not None
            and row["replay_signature"]["continuation_exit_class"] != "timeout"
            and row["strict_timed_out"] is not True
            for row in outcomes
        ),
    }
    passed = all(gates.values())
    return {
        "counts": {
            "project_count": len({state["project_family"] for state in states}),
            "state_count": len(states),
            "action_branch_count": len(outcomes),
            "reference_closure_count": len(reference_closures),
            "states_by_build_system": dict(
                sorted(Counter(state["build_system"] for state in states).items())
            ),
            "optimal_actions": dict(
                sorted(Counter(label["optimal_action"] for label in labels).items())
            ),
            "optimal_project_families": {
                family: len(projects)
                for family, projects in sorted(optimal_projects.items())
            },
        },
        "replay": replay,
        "labels": labels,
        "rule_gate": rule_gate,
        "tfidf_logistic_regression": tfidf,
        "leakage_audit": leakage,
        "gates": gates,
        "passed": passed,
        "decision": manifest["decision_rule"]["pass"]
        if passed
        else manifest["decision_rule"]["fail"],
        "thresholds_adjusted_after_results": False,
        "provider_calls": 0,
        "credential_reads": 0,
        "model_calls": 0,
        "model_tokens": 0,
    }


def run_pilot(
    manifest: dict[str, Any],
    pool: dict[str, Any],
    *,
    output_json: Path,
    output_markdown: Path,
    work_root: Path | None = None,
) -> dict[str, Any]:
    if output_json.exists() or output_markdown.exists():
        raise PilotError("输出已存在，禁止覆盖、续跑或 backfill")
    readiness = preflight(manifest, pool)
    image = readiness["image_id"]
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if work_root is None:
        temporary = tempfile.TemporaryDirectory(prefix="forge-semantic-routing-v2-")
        root = Path(temporary.name)
    else:
        root = work_root.resolve()
        root.mkdir(parents=True, exist_ok=False)
    states_by_id: dict[str, dict[str, Any]] = {}
    outcomes: list[dict[str, Any]] = []
    reference_closures: list[dict[str, Any]] = []
    hidden_mapping: dict[str, str] = {}
    try:
        for task in pool["tasks"]:
            for replicate in range(1, manifest["environment"]["replicates"] + 1):
                project_root = root / f"{task['task_id']}-replicate-{replicate}"
                project_root.mkdir()
                project_states, project_outcomes, closure, mapping = (
                    _run_project_replicate(
                        manifest=manifest,
                        image=image,
                        task=task,
                        replicate=replicate,
                        root=project_root,
                    )
                )
                if replicate == 1:
                    for state in project_states:
                        states_by_id[state["state_id"]] = state
                    hidden_mapping.update(mapping)
                else:
                    for state in project_states:
                        if state["state_id"] not in states_by_id:
                            raise PilotError("replicate state identity 漂移")
                outcomes.extend(project_outcomes)
                reference_closures.append(closure)
        states = sorted(states_by_id.values(), key=lambda item: item["state_id"])
        outcomes.sort(
            key=lambda item: (
                item["state_id"],
                item["action_family"],
                item["replicate"],
            )
        )
        analysis = analyse_results(manifest, states, outcomes, reference_closures)
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "document_type": "forge_typed_semantic_routing_pilot_report",
            "identity": IDENTITY,
            "issue_url": ISSUE_URL,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "completed",
            "git_branch": readiness["git_branch"],
            "git_commit": readiness["git_commit"],
            "manifest_canonical_sha256": v1.canonical_sha256(manifest),
            "source_pool_canonical_sha256": v1.canonical_sha256(pool),
            "image_id": image,
            "states": states,
            "hidden_fault_mapping": dict(sorted(hidden_mapping.items())),
            "outcomes": outcomes,
            "reference_closures": reference_closures,
            "analysis": analysis,
            "interpretation": {
                "benchmark_difficulty_gate_passed": analysis["passed"],
                "jev_model_effect_estimated": False,
                "controller_effect_estimated": False,
                "escalation_surrogate_is_agent_effect": False,
                "historical_evidence_modified": False,
            },
        }
        validate_report(report, manifest, pool)
        v1.write_once(
            output_json,
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        v1.write_once(output_markdown, render_markdown(report))
        return report
    finally:
        v1.require_zero_managed_resources()
        if temporary is not None:
            temporary.cleanup()


def validate_report(
    report: dict[str, Any], manifest: dict[str, Any], pool: dict[str, Any]
) -> dict[str, Any]:
    validate_manifest(manifest, pool)
    if (
        report.get("schema_version") != REPORT_SCHEMA_VERSION
        or report.get("identity") != IDENTITY
    ):
        raise PilotError("report identity 无效")
    if report.get("status") != "completed":
        raise PilotError("report 未闭合")
    if report.get("manifest_canonical_sha256") != v1.canonical_sha256(manifest):
        raise PilotError("report manifest hash 漂移")
    if report.get("source_pool_canonical_sha256") != v1.canonical_sha256(pool):
        raise PilotError("report source pool hash 漂移")
    states = report.get("states")
    outcomes = report.get("outcomes")
    closures = report.get("reference_closures")
    if (
        not isinstance(states, list)
        or not isinstance(outcomes, list)
        or not isinstance(closures, list)
    ):
        raise PilotError("report 原始矩阵缺失")
    regenerated = analyse_results(manifest, states, outcomes, closures)
    if report.get("analysis") != regenerated:
        raise PilotError("report 分析无法从 outcome matrix 确定重建")
    mapping = report.get("hidden_fault_mapping")
    if not isinstance(mapping, dict) or set(mapping) != {
        state["state_id"] for state in states
    }:
        raise PilotError("hidden fault mapping 不完整")
    if Counter(mapping.values()) != {fault: 6 for fault in FAULT_TYPES}:
        raise PilotError("hidden fault 配额漂移")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    analysis = report["analysis"]
    if set(analysis["gates"]) != set(GATE_ORDER):
        raise PilotError("report 门禁集合漂移")
    gates = "\n".join(
        f"| `{name}` | {'通过' if analysis['gates'][name] else '失败'} |"
        for name in GATE_ORDER
    )
    systems = "\n".join(
        f"| {name} | {analysis['counts']['states_by_build_system'].get(name, 0)} |"
        for name in BUILD_SYSTEMS
    )
    optimal = "\n".join(
        f"| {name} | {analysis['counts']['optimal_actions'].get(name, 0)} | "
        f"{analysis['counts']['optimal_project_families'].get(name, 0)} |"
        for name in ACTION_FAMILIES
    )
    if analysis["passed"]:
        conclusion = (
            "v2 同阶段异根因 benchmark 通过零 Provider 难度门禁。简单 RuleGate 与项目族隔离的 TF-IDF/逻辑回归均未饱和，"
            "因此存在进入独立 Jev 离线资格实验的可辨识空间。"
        )
    else:
        failed = ", ".join(
            name for name in GATE_ORDER if not analysis["gates"][name]
        )
        conclusion = (
            "v2 未通过零 Provider 难度门禁，停止 Jev Provider 资格。失败门禁为："
            f"{failed}。该结果评价 benchmark 设计，不是 Jev 模型效果。"
        )
    protocol_summary = (
        "本轮在完全相同的 coarse phase facts 下，对 6 个项目各构造 3 个故障状态。"
        "每个 state/action pair 执行两次，候选动作后统一运行 build、artifact stage、"
        "functional oracle、provenance 和 clean replay。最优动作由 strict success 优先、"
        "冻结成本次优确定，没有使用旧 Agent 行为或人工故障类别作标签。"
    )
    interpretation_boundary = (
        "本 pilot 只回答 benchmark 是否能在相同阶段事实下形成异根因、异最优动作，并抵抗两个零 Provider 基线。"
        "它没有调用 Jev 或通用 LLM，不估计 confidence、费用、延迟、controller 成功率或端到端 treatment effect。"
        "`escalate_agent` 使用确定性零 Provider recovery surrogate，只保证每个状态存在兜底路径，不代表真实 Agent 效果。"
    )
    return f"""# 同阶段异根因类型化语义路由 benchmark v2 结果

- identity：`{IDENTITY}`
- tracking Issue：[#391]({ISSUE_URL})
- 执行 revision：`{report["git_commit"]}`
- 决定：`{analysis["decision"]}`

## 关键结论

{conclusion}

{protocol_summary}

## 结果

- 项目：`{analysis["counts"]["project_count"]}`
- 状态：`{analysis["counts"]["state_count"]}`
- action branches：`{analysis["counts"]["action_branch_count"]}`
- reference closures：`{analysis["counts"]["reference_closure_count"]}`
- categorical replay 一致率：`{analysis["replay"]["replay_consistency"]:.4f}`
- RuleGate top-1：`{analysis["rule_gate"]["top1_accuracy"]:.4f}`
- RuleGate route-acceptable coverage：`{analysis["rule_gate"]["route_acceptable_coverage"]:.4f}`
- LOPO TF-IDF/逻辑回归 top-1：`{analysis["tfidf_logistic_regression"]["top1_accuracy"]:.4f}`

| 构建系统 | 状态数 |
|---|---:|
{systems}

| 最优动作 | 状态数 | project family 数 |
|---|---:|---:|
{optimal}

| 门禁 | 结果 |
|---|---|
{gates}

## 解释边界

{interpretation_boundary}

Provider `0` 次、credential `0` 次、模型调用 `0` 次、模型 token `0`；历史 evidence 保持只读。
"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("generate")
    subparsers.add_parser("validate")
    subparsers.add_parser("preflight")
    run = subparsers.add_parser("run")
    run.add_argument("--work-root", type=Path)
    run.add_argument("--json-output", type=Path, default=DEFAULT_JSON_REPORT)
    run.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_REPORT)
    validate_result = subparsers.add_parser("validate-report")
    validate_result.add_argument("--report", type=Path, default=DEFAULT_JSON_REPORT)
    render = subparsers.add_parser("render-report")
    render.add_argument("--report", type=Path, default=DEFAULT_JSON_REPORT)
    render.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "generate":
        generate_contract_files()
        print(v1.canonical_sha256(v1.load_json(DEFAULT_MANIFEST)))
        return 0
    manifest, pool = load_contract()
    if args.command == "validate":
        print(v1.canonical_sha256(manifest))
        return 0
    if args.command == "preflight":
        print(
            json.dumps(
                preflight(manifest, pool, require_clean=False),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "run":
        report = run_pilot(
            manifest,
            pool,
            output_json=args.json_output,
            output_markdown=args.markdown_output,
            work_root=args.work_root,
        )
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "decision": report["analysis"]["decision"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "validate-report":
        report = validate_report(v1.load_json(args.report), manifest, pool)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "decision": report["analysis"]["decision"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    report = validate_report(v1.load_json(args.report), manifest, pool)
    args.output.write_text(render_markdown(report), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Issue #457 进展预算感知 Jev 联合 benchmark 零 Provider 资格。"""

from __future__ import annotations

import argparse
import copy
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
import forge_typed_semantic_routing_pilot_v2 as semantic_v2
import jsonschema


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
IDENTITY = "cpp-progress-budget-jev-identifiability-qualification-v1"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/457"
BRANCH = "yiwei/457-progress-budget-jev-identifiability"
SCHEMA_VERSION = "forge-progress-budget-jev-identifiability-qualification-1.0.0"
REPORT_SCHEMA_VERSION = (
    "forge-progress-budget-jev-identifiability-qualification-report-1.0.0"
)
SOURCE_POOL_SCHEMA_VERSION = (
    "forge-progress-budget-jev-identifiability-source-pool-1.0.0"
)

DEFAULT_SOURCE_POOL = (
    REPO_ROOT
    / "benchmarks/fixtures/cpp-progress-budget-jev-identifiability-source-pool-v1.json"
)
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "benchmarks/manifests/cpp-progress-budget-jev-identifiability-qualification-v1.json"
)
DEFAULT_SCHEMA = (
    REPO_ROOT
    / "benchmarks/schemas/forge-progress-budget-jev-identifiability-qualification-v1.schema.json"
)
DEFAULT_JSON_REPORT = (
    REPO_ROOT
    / "benchmarks/reports/cpp-progress-budget-jev-identifiability-qualification-v1.json"
)
DEFAULT_MARKDOWN_REPORT = (
    REPO_ROOT
    / "benchmarks/reports/cpp-progress-budget-jev-identifiability-qualification-v1.md"
)
PREREGISTRATION = (
    REPO_ROOT
    / "benchmarks/preregistrations/cpp-progress-budget-jev-identifiability-qualification-v1.md"
)
SPEC_PATH = (
    REPO_ROOT / "docs/research/2026-10-14-progress-budget-jev-identifiability-spec.md"
)
PLAN_PATH = (
    REPO_ROOT / "docs/research/2026-10-14-progress-budget-jev-identifiability-plan.md"
)
EVIDENCE_ROOT = (
    REPO_ROOT
    / ".compile-sessions/benchmark-evidence-progress-budget-jev-identifiability-qualification-v1"
)
USER_UNTRACKED_ALLOWLIST = {
    "?? docs/research/2026-10-13-forge-research-progress-defense.html"
}

BUILD_SYSTEMS = ("cmake", "make", "autotools")
FAULT_TYPES = (
    "missing_compile_input",
    "invalid_build_state",
    "wrong_build_target",
    "compound_recovery",
    "replay_recipe_gap",
)
ACTION_FAMILIES = ("dependency", "configure", "build", "escalate_agent")
ACTION_COSTS = {
    "build": 1,
    "configure": 2,
    "dependency": 3,
    "escalate_agent": 6,
}
OPAQUE_TARGET = "forge_probe_457_a91c"
MARKER_HEADER = "forge_replay_marker.h"
MARKER_COMPILER = "forge-cc"
AGENT_RESERVATION = {
    "wall_clock_milliseconds": 300_000,
    "provider_requests": 12,
    "input_tokens": 150_000,
    "output_tokens": 15_000,
    "provider_cost_microusd": 60_000,
    "build_executions": 2,
}
BUDGET_PROFILES = {
    "critical": {
        "wall_clock_milliseconds": 30_000,
        "provider_requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "provider_cost_microusd": 0,
        "build_executions": 1,
    },
    "local_only": {
        "wall_clock_milliseconds": 180_000,
        "provider_requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "provider_cost_microusd": 0,
        "build_executions": 3,
    },
    "agent_capable": {
        "wall_clock_milliseconds": 360_000,
        "provider_requests": 12,
        "input_tokens": 150_000,
        "output_tokens": 15_000,
        "provider_cost_microusd": 60_000,
        "build_executions": 3,
    },
}
DIRECT_ROUTE_CHARGES = {
    "build": {
        "wall_clock_milliseconds": 120_000,
        "provider_requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "provider_cost_microusd": 0,
        "build_executions": 3,
    },
    "configure": {
        "wall_clock_milliseconds": 120_000,
        "provider_requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "provider_cost_microusd": 0,
        "build_executions": 2,
    },
    "dependency": {
        "wall_clock_milliseconds": 120_000,
        "provider_requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "provider_cost_microusd": 0,
        "build_executions": 2,
    },
}
BUILD_FAILED_PHASE_FACTS = {
    "source_available": True,
    "configured": True,
    "build_attempted": True,
    "build_succeeded": False,
    "artifacts_staged": False,
    "functional_oracle_passed": False,
    "replay_closure_ready": False,
    "strict_verifier_passed": False,
}
REPLAY_REJECTED_PHASE_FACTS = {
    "source_available": True,
    "configured": True,
    "build_attempted": True,
    "build_succeeded": True,
    "artifacts_staged": True,
    "functional_oracle_passed": True,
    "replay_closure_ready": False,
    "strict_verifier_passed": False,
}
GATE_ORDER = (
    "expected_counts",
    "reference_closure",
    "replay_consistency",
    "cross_system_action_and_route_support",
    "rule_gate_below_ceiling",
    "tfidf_budgetfit_below_ceiling",
    "matched_budget_changes_route",
    "replay_rejection_and_recovery",
    "no_direct_label_leakage",
    "bounded_execution",
    "budget_and_observation_closure",
    "zero_provider_boundary",
    "cleanup",
)


class QualificationError(RuntimeError):
    """资格合同、执行环境或 evidence 不满足冻结要求。"""


def _task(
    *,
    fault_file: str,
    configure_repair_commands: list[str],
    replay_setup_commands: list[str],
    replay_configure_commands: list[str],
    replay_build_commands: list[str],
    **kwargs: Any,
) -> dict[str, Any]:
    task = v1._task(**kwargs)
    task["project_family"] = v1.normalize_project_family(task["repository_url"])
    task["fault_file"] = fault_file
    task["configure_repair_commands"] = configure_repair_commands
    task["replay_setup_commands"] = replay_setup_commands
    task["replay_configure_commands"] = replay_configure_commands
    task["replay_build_commands"] = replay_build_commands
    return task


def _marker_header_command() -> str:
    return f"printf '%s\\n' '#pragma once' > {MARKER_HEADER}"


def _marker_compiler_commands() -> list[str]:
    wrapper = (
        '#!/bin/sh\nexec gcc-13 -include /workspace/repo/forge_replay_marker.h "$@"'
    )
    encoded = __import__("base64").b64encode(wrapper.encode()).decode()
    return [
        _marker_header_command(),
        f"printf %s {shlex.quote(encoded)} | base64 -d > {MARKER_COMPILER}",
        f"chmod +x {MARKER_COMPILER}",
    ]


TASKS = (
    _task(
        task_id="argparse",
        repository_url="https://github.com/p-ranav/argparse.git",
        commit_sha="7d093f8e1201db2dded2eee94de77665698ee9dc",
        commit_committed_at="2026-10-04T20:35:26-04:00",
        source_snapshot_sha256="03e064de0c914c4b4fadc4eb40a3cfff57cff9364cfa4b6895730132e142eed9",
        license_path="LICENSE",
        license_sha256="a3a9e0dc669644b703773777503f73abff8dffacc4e697d8535be930766fa771",
        build_system="cmake",
        configure_commands=[
            "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release "
            "-DARGPARSE_BUILD_TESTS=OFF -DARGPARSE_BUILD_SAMPLES=ON "
            "-DARGPARSE_INSTALL=OFF"
        ],
        build_commands=[
            "cmake --build build --target ARGPARSE_SAMPLE_positional_argument --parallel 4"
        ],
        artifact_stage_commands=[
            "install -Dm755 build/samples/positional_argument /artifacts/positional_argument"
        ],
        required_artifacts=["positional_argument"],
        artifact_types=["executable"],
        oracle={"kind": "command", "argv": ["/artifacts/positional_argument", "7"]},
        tracked_file_count=83,
        fault_file="include/argparse/argparse.hpp",
        configure_repair_commands=[
            "rm -rf build",
            "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release "
            "-DARGPARSE_BUILD_TESTS=OFF -DARGPARSE_BUILD_SAMPLES=ON "
            "-DARGPARSE_INSTALL=OFF",
        ],
        replay_setup_commands=[_marker_header_command()],
        replay_configure_commands=[
            "cmake -S . -B build-replay -DCMAKE_BUILD_TYPE=Release "
            "-DARGPARSE_BUILD_TESTS=OFF -DARGPARSE_BUILD_SAMPLES=ON "
            "-DARGPARSE_INSTALL=OFF "
            "'-DCMAKE_CXX_FLAGS=-include /workspace/repo/forge_replay_marker.h'"
        ],
        replay_build_commands=[
            "cmake --build build-replay --target ARGPARSE_SAMPLE_positional_argument --parallel 4",
            "mkdir -p build/samples && cp build-replay/samples/positional_argument build/samples/positional_argument",
        ],
    ),
    _task(
        task_id="magic-enum",
        repository_url="https://github.com/Neargye/magic_enum.git",
        commit_sha="5de969c9005938a27a34d3af3ea5923d18679ad8",
        commit_committed_at="2026-10-05T19:05:16+04:00",
        source_snapshot_sha256="26eb732eaa8f9dcc5c3e3998db4bcdcc2402b61bed3fdcf899c93276356ff5ed",
        license_path="LICENSE",
        license_sha256="7240d196079161cabea66b2b4e52d83d0946ab74900ea4dacd5e50d6bcac4510",
        build_system="cmake",
        configure_commands=[
            "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release "
            "-DMAGIC_ENUM_OPT_BUILD_EXAMPLES=ON -DMAGIC_ENUM_OPT_BUILD_TESTS=OFF "
            "-DMAGIC_ENUM_OPT_VERIFY_INTERFACE_HEADER_SETS=OFF -DMAGIC_ENUM_OPT_INSTALL=OFF"
        ],
        build_commands=["cmake --build build --target example --parallel 4"],
        artifact_stage_commands=[
            "install -Dm755 build/example/example /artifacts/magic-enum-example"
        ],
        required_artifacts=["magic-enum-example"],
        artifact_types=["executable"],
        oracle={"kind": "command", "argv": ["/artifacts/magic-enum-example"]},
        tracked_file_count=85,
        fault_file="include/magic_enum/magic_enum.hpp",
        configure_repair_commands=[
            "rm -rf build",
            "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release "
            "-DMAGIC_ENUM_OPT_BUILD_EXAMPLES=ON -DMAGIC_ENUM_OPT_BUILD_TESTS=OFF "
            "-DMAGIC_ENUM_OPT_VERIFY_INTERFACE_HEADER_SETS=OFF -DMAGIC_ENUM_OPT_INSTALL=OFF",
        ],
        replay_setup_commands=[_marker_header_command()],
        replay_configure_commands=[
            "cmake -S . -B build-replay -DCMAKE_BUILD_TYPE=Release "
            "-DMAGIC_ENUM_OPT_BUILD_EXAMPLES=ON -DMAGIC_ENUM_OPT_BUILD_TESTS=OFF "
            "-DMAGIC_ENUM_OPT_VERIFY_INTERFACE_HEADER_SETS=OFF -DMAGIC_ENUM_OPT_INSTALL=OFF "
            "'-DCMAKE_CXX_FLAGS=-include /workspace/repo/forge_replay_marker.h'"
        ],
        replay_build_commands=[
            "cmake --build build-replay --target example --parallel 4",
            "mkdir -p build/example && cp build-replay/example/example build/example/example",
        ],
    ),
    _task(
        task_id="parson",
        repository_url="https://github.com/kgabis/parson.git",
        commit_sha="ec53fb6528b45811df9db0db22cab96a94a96a11",
        commit_committed_at="2026-09-15T13:24:18+02:00",
        source_snapshot_sha256="85f7c75728b1a7f73cbd68c614270f007ae8e8f2ce00f0c33e87879eae0687d1",
        license_path="LICENSE",
        license_sha256="ea4347d6cdbf46b37f436d02150fc7c4167280e8d0c3269b5d61ef1d0a002542",
        build_system="make",
        configure_commands=["test -f Makefile"],
        build_commands=["make test"],
        artifact_stage_commands=["install -Dm755 test /artifacts/parson-test"],
        required_artifacts=["parson-test"],
        artifact_types=["executable"],
        oracle={"kind": "command", "argv": ["/artifacts/parson-test"]},
        tracked_file_count=19,
        fault_file="parson.c",
        configure_repair_commands=["git checkout HEAD -- Makefile", "test -f Makefile"],
        replay_setup_commands=_marker_compiler_commands(),
        replay_configure_commands=["test -f Makefile"],
        replay_build_commands=["make CC=./forge-cc test"],
    ),
    _task(
        task_id="sds",
        repository_url="https://github.com/antirez/sds.git",
        commit_sha="5347739b1581fcba74fd5cab1fc21d2aef317d71",
        commit_committed_at="2025-04-18T12:59:31+02:00",
        source_snapshot_sha256="087af82e8d0993efb8cd283fb21f2eea467099bfeb07d87b3dd38fbb07b1fe9f",
        license_path="LICENSE",
        license_sha256="bb0d0d505009fdf584b0f44dbb62562eebada497d53d726cd2e940ada512dc16",
        build_system="make",
        configure_commands=["test -f Makefile"],
        build_commands=["make -j4"],
        artifact_stage_commands=["install -Dm755 sds-test /artifacts/sds-test"],
        required_artifacts=["sds-test"],
        artifact_types=["executable"],
        oracle={"kind": "command", "argv": ["/artifacts/sds-test"]},
        tracked_file_count=9,
        fault_file="sds.c",
        configure_repair_commands=["git checkout HEAD -- Makefile", "test -f Makefile"],
        replay_setup_commands=_marker_compiler_commands(),
        replay_configure_commands=["test -f Makefile"],
        replay_build_commands=["make CC=./forge-cc -j4"],
    ),
    _task(
        task_id="libuev",
        repository_url="https://github.com/troglobit/libuev.git",
        commit_sha="c964bbe8fb154db486d33369e3ad101992c50979",
        commit_committed_at="2025-04-28T08:35:10+02:00",
        source_snapshot_sha256="b24c7dbb30acf60b86bcebf040bfd3fca008c0b395d15b5efd487c408017ecc0",
        license_path="LICENSE",
        license_sha256="387d0d8e2aabf187751c8f1ebb9a4abaecaa7e0e05fead27f408193a0f0f17dd",
        build_system="autotools",
        configure_commands=[
            "./autogen.sh",
            "./configure --prefix=/artifacts --disable-shared --enable-static --disable-examples",
        ],
        build_commands=["make -j4"],
        artifact_stage_commands=["make install"],
        required_artifacts=["include/uev/uev.h", "lib/libuev.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <uev/uev.h>\nint main(void){uev_ctx_t ctx; return uev_init(&ctx) < 0;}\n",
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libuev.a",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=66,
        fault_file="src/uev.c",
        configure_repair_commands=[
            "./autogen.sh",
            "./configure --prefix=/artifacts --disable-shared --enable-static --disable-examples",
        ],
        replay_setup_commands=_marker_compiler_commands(),
        replay_configure_commands=[
            "./autogen.sh",
            "CC=/workspace/repo/forge-cc ./configure --prefix=/artifacts "
            "--disable-shared --enable-static --disable-examples",
        ],
        replay_build_commands=["make -j4"],
    ),
    _task(
        task_id="libatomic-ops",
        repository_url="https://github.com/ivmai/libatomic_ops.git",
        commit_sha="c7901207f871e80c973bfeae71f04f7b59c69636",
        commit_committed_at="2026-09-25T14:17:28+03:00",
        source_snapshot_sha256="d773731355a6ab226b1b86aa6b76af837cd53139675dd5fbdea109aa8624e314",
        license_path="LICENSE",
        license_sha256="969294c9324b2d360ae2a08edd5ca6f9cd754cb71b71e56bee15d2f10bb10496",
        build_system="autotools",
        configure_commands=[
            "./autogen.sh",
            "./configure --prefix=/artifacts --disable-shared --enable-static --disable-gpl",
        ],
        build_commands=["make -j4"],
        artifact_stage_commands=["make install"],
        required_artifacts=["include/atomic_ops.h", "lib/libatomic_ops.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <atomic_ops.h>\nint main(void){volatile AO_t x=0; AO_store(&x,7); return AO_load(&x)==7 ? 0 : 1;}\n",
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libatomic_ops.a",
                "-lpthread",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=119,
        fault_file="src/atomic_ops.c",
        configure_repair_commands=[
            "./autogen.sh",
            "./configure --prefix=/artifacts --disable-shared --enable-static --disable-gpl",
        ],
        replay_setup_commands=_marker_compiler_commands(),
        replay_configure_commands=[
            "./autogen.sh",
            "CC=/workspace/repo/forge-cc ./configure --prefix=/artifacts "
            "--disable-shared --enable-static --disable-gpl",
        ],
        replay_build_commands=["make -j4"],
    ),
)


def generate_source_pool() -> dict[str, Any]:
    return {
        "schema_version": SOURCE_POOL_SCHEMA_VERSION,
        "identity": IDENTITY,
        "selection_status": "frozen_before_formal_outcomes",
        "quotas": {"project_count": 6, "projects_per_build_system": 2},
        "role": "benchmark_design_and_qualification_only",
        "future_evaluation_contract": {
            "project_families_must_be_disjoint": True,
            "commit_must_be_later_than": max(
                task["commit_committed_at"] for task in TASKS
            ),
        },
        "selection_audit": {
            "included_project_ids": [task["task_id"] for task in TASKS],
            "excluded_before_freeze": [
                {
                    "project_family": "github.com/rxi/log.c",
                    "reason": "no_project_level_build_entrypoint",
                    "formal_outcome_observed": False,
                },
                {
                    "project_family": "github.com/tidwall/hashmap.c",
                    "reason": "no_project_level_build_entrypoint",
                    "formal_outcome_observed": False,
                },
                {
                    "project_family": "github.com/ebiggers/libdeflate",
                    "reason": "make_quota_filled_by_native_make_project",
                    "formal_outcome_observed": False,
                },
            ],
        },
        "tasks": list(TASKS),
    }


def generate_manifest(source_pool: dict[str, Any] | None = None) -> dict[str, Any]:
    pool = source_pool or generate_source_pool()
    return {
        "$schema": "../schemas/forge-progress-budget-jev-identifiability-qualification-v1.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": "forge_progress_budget_jev_identifiability_qualification",
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "status": "authorized_zero_provider_qualification",
        "authorization": {
            "public_source_network": True,
            "docker_execution": True,
            "new_identity_evidence_write": True,
            "credential_read": False,
            "provider_calls": False,
            "jev_calls": False,
            "agent_calls": False,
            "model_tokens": 0,
            "controller_implementation": False,
            "historical_evidence_write": False,
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
        "design": {
            "fault_types": list(FAULT_TYPES),
            "actions": list(ACTION_FAMILIES),
            "action_costs": ACTION_COSTS,
            "budget_profiles": BUDGET_PROFILES,
            "direct_route_charges": DIRECT_ROUTE_CHARGES,
            "agent_reservation": AGENT_RESERVATION,
            "label_rule": "two_replicate_strict_safety_then_budget_feasibility_then_frozen_cost",
            "strict_checks": [
                "candidate",
                "functional",
                "provenance",
                "clean_replay",
            ],
            "shell_generation_by_model": False,
            "agent_execution": "zero_provider_deterministic_recovery_surrogate",
            "agent_reservation_is_observed_provider_usage": False,
        },
        "baselines": {
            "phase_budget_rule_gate": {
                "semantic_log": False,
                "progress_history": False,
                "rule": "critical_stop_replay_dependency_else_build",
            },
            "log_tfidf_budgetfit": {
                "input": "semantic_failure_log_only",
                "split": "leave_one_project_family_out",
                "ngram_range": [1, 2],
                "max_features": 5000,
                "solver": "liblinear_one_vs_rest",
                "budget_fit": True,
                "progress_history": False,
            },
        },
        "thresholds": {
            "minimum_replay_consistency": 0.95,
            "maximum_rule_gate_route_accuracy_exclusive": 0.75,
            "maximum_tfidf_budgetfit_route_accuracy_exclusive": 0.95,
            "minimum_states_with_budget_route_change": 30,
            "required_replay_rejections": 12,
            "required_replay_dependency_recoveries": 12,
        },
        "decision_rule": {
            "pass": "proceed_to_jev_progress_budget_calibration_design",
            "fail": "stop_before_jev_calibration_and_controller_implementation",
            "retry": False,
            "replacement": False,
            "backfill": False,
            "threshold_adjustment_after_results": False,
        },
        "evidence": {
            "root": EVIDENCE_ROOT.relative_to(REPO_ROOT).as_posix(),
            "create_once": True,
            "attempt_limit": 1,
            "inventory_excludes": ["inventory.json", "completed.json"],
        },
        "documents": {
            "preregistration": PREREGISTRATION.relative_to(REPO_ROOT).as_posix(),
            "spec": SPEC_PATH.relative_to(REPO_ROOT).as_posix(),
            "plan": PLAN_PATH.relative_to(REPO_ROOT).as_posix(),
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
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-progress-budget-jev-identifiability-qualification-v1.schema.json",
        "title": "Forge progress budget Jev identifiability qualification v1",
        "const": manifest,
    }


def _safe_relative(value: str) -> None:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise QualificationError(f"不安全的相对路径: {value}")


def validate_source_pool(pool: dict[str, Any]) -> dict[str, Any]:
    if (
        pool.get("schema_version") != SOURCE_POOL_SCHEMA_VERSION
        or pool.get("identity") != IDENTITY
    ):
        raise QualificationError("source pool identity 漂移")
    tasks = pool.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 6:
        raise QualificationError("source pool 必须包含 6 个项目")
    if Counter(task["selected_build_system"] for task in tasks) != {
        name: 2 for name in BUILD_SYSTEMS
    }:
        raise QualificationError("build system 配额漂移")
    if len({task["project_family"] for task in tasks}) != 6:
        raise QualificationError("project family 未隔离")
    for task in tasks:
        if task["project_family"] != v1.normalize_project_family(
            task["repository_url"]
        ):
            raise QualificationError(f"{task['task_id']} project family 漂移")
        if v1.HEX40.fullmatch(task["commit_sha"]) is None:
            raise QualificationError(f"{task['task_id']} exact commit 无效")
        for name in ("source_snapshot_sha256", "license_sha256"):
            if v1.HEX64.fullmatch(task[name]) is None:
                raise QualificationError(f"{task['task_id']} {name} 无效")
        for path in (
            task["license_path"],
            task["fault_file"],
            *task["target"]["required_artifacts"],
        ):
            _safe_relative(path)
        commands = [
            *task["configure_commands"],
            *task["configure_repair_commands"],
            *task["build_commands"],
            *task["artifact_stage_commands"],
            *task["replay_setup_commands"],
            *task["replay_configure_commands"],
            *task["replay_build_commands"],
        ]
        forbidden = (
            "curl ",
            "wget ",
            "git clone",
            "git fetch",
            "apt-get",
            "sudo ",
        )
        if any(token in command for command in commands for token in forbidden):
            raise QualificationError(f"{task['task_id']} 动作包含网络或提权")
    exclusions = pool["selection_audit"]["excluded_before_freeze"]
    if len(exclusions) != 3 or any(
        row["formal_outcome_observed"] for row in exclusions
    ):
        raise QualificationError("结果盲排除审计漂移")
    return pool


def validate_manifest(
    manifest: dict[str, Any], pool: dict[str, Any], *, check_schema: bool = True
) -> dict[str, Any]:
    validate_source_pool(pool)
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("identity") != IDENTITY
    ):
        raise QualificationError("manifest identity 漂移")
    auth = manifest.get("authorization", {})
    for key in (
        "credential_read",
        "provider_calls",
        "jev_calls",
        "agent_calls",
        "controller_implementation",
        "historical_evidence_write",
    ):
        if auth.get(key) is not False:
            raise QualificationError(f"manifest 意外授权 {key}")
    if auth.get("model_tokens") != 0:
        raise QualificationError("model token 边界漂移")
    if manifest["source_pool"]["canonical_sha256"] != v1.canonical_sha256(pool):
        raise QualificationError("source pool hash 漂移")
    if manifest["design"]["budget_profiles"] != BUDGET_PROFILES:
        raise QualificationError("budget profile 漂移")
    if check_schema:
        schema = v1.load_json(DEFAULT_SCHEMA)
        if schema != generate_schema(manifest):
            raise QualificationError("const schema 漂移")
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


def _meaningful_status() -> list[str]:
    return [
        line
        for line in _git_output("status", "--porcelain").splitlines()
        if line not in USER_UNTRACKED_ALLOWLIST
    ]


def preflight(
    manifest: dict[str, Any], pool: dict[str, Any], *, require_clean: bool = True
) -> dict[str, Any]:
    v1.require_zero_managed_resources()
    image_id = v1.current_image_id(manifest)
    if _git_output("branch", "--show-current") != BRANCH:
        raise QualificationError("正式 outcome 分支漂移")
    if require_clean and _meaningful_status():
        raise QualificationError("正式 outcome 前存在非 allowlist 工作树变化")
    if require_clean:
        try:
            upstream = _git_output("rev-parse", "@{upstream}")
        except Exception as exc:
            raise QualificationError("正式 outcome 前分支必须已推送") from exc
        if upstream != _git_output("rev-parse", "HEAD"):
            raise QualificationError("正式 outcome revision 尚未完整推送")
    for path in (PREREGISTRATION, SPEC_PATH, PLAN_PATH):
        if not path.is_file():
            raise QualificationError(f"缺少冻结文档: {path.name}")
    if (
        EVIDENCE_ROOT.exists()
        or DEFAULT_JSON_REPORT.exists()
        or DEFAULT_MARKDOWN_REPORT.exists()
    ):
        raise QualificationError("create-once evidence 或报告已存在")
    return {
        "ready": True,
        "identity": IDENTITY,
        "git_branch": BRANCH,
        "git_commit": _git_output("rev-parse", "HEAD"),
        "image_id": image_id,
        "project_count": len(pool["tasks"]),
        "state_count": 30,
        "action_branch_count": 240,
        "budget_decision_count": 90,
        "provider_calls": 0,
        "credential_reads": 0,
        "jev_calls": 0,
        "agent_calls": 0,
        "model_tokens": 0,
    }


def _state_id(task: dict[str, Any], fault_type: str) -> str:
    digest = hashlib.sha256(
        f"{IDENTITY}|{task['project_family']}|{fault_type}".encode()
    ).hexdigest()
    return f"s-{digest[:20]}"


def _dependency_commands(task: dict[str, Any]) -> list[str]:
    return [f"git checkout HEAD -- {shlex.quote(task['fault_file'])}"]


def _action_commands(task: dict[str, Any], fault_type: str, family: str) -> list[str]:
    if fault_type == "replay_recipe_gap":
        if family == "dependency":
            return list(task["replay_setup_commands"])
        if family == "configure":
            return list(task["replay_configure_commands"])
        if family == "build":
            return list(task["replay_build_commands"])
        if family == "escalate_agent":
            return [
                *task["replay_setup_commands"],
                *task["replay_configure_commands"],
            ]
    else:
        if family == "dependency":
            return _dependency_commands(task)
        if family == "configure":
            return list(task["configure_repair_commands"])
        if family == "build":
            return list(task["build_commands"])
        if family == "escalate_agent":
            return [
                *_dependency_commands(task),
                *task["configure_repair_commands"],
            ]
    raise QualificationError(f"未知 action: {fault_type}/{family}")


def _progress_facts(fault_type: str) -> dict[str, Any]:
    if fault_type == "compound_recovery":
        return {
            "last_action_family": "diagnostic_probe",
            "last_action_changed_frontier": False,
            "repeated_failure_signature_count": 2,
            "unresolved_obligation_count": 2,
            "latest_verified_frontier": "configured",
        }
    if fault_type == "replay_recipe_gap":
        return {
            "last_action_family": "submit",
            "last_action_changed_frontier": True,
            "repeated_failure_signature_count": 1,
            "unresolved_obligation_count": 1,
            "latest_verified_frontier": "workspace_candidate_ready",
        }
    return {
        "last_action_family": "build",
        "last_action_changed_frontier": fault_type == "wrong_build_target",
        "repeated_failure_signature_count": 1,
        "unresolved_obligation_count": 1,
        "latest_verified_frontier": "configured",
    }


def _state_record(
    task: dict[str, Any], fault_type: str, semantic_log: str
) -> dict[str, Any]:
    state_id = _state_id(task, fault_type)
    phase_facts = (
        REPLAY_REJECTED_PHASE_FACTS
        if fault_type == "replay_recipe_gap"
        else BUILD_FAILED_PHASE_FACTS
    )
    progress_facts = _progress_facts(fault_type)
    actions = [
        {
            "action_id": f"{state_id}:{family}",
            "action_family": family,
            "bound_commands": _action_commands(task, fault_type, family),
            "cost": ACTION_COSTS[family],
            "executor": "zero_provider_recovery_surrogate"
            if family == "escalate_agent"
            else "docker_command",
            "direct_execution": family != "escalate_agent",
        }
        for family in ACTION_FAMILIES
    ]
    return {
        "state_id": state_id,
        "project_id": task["task_id"],
        "project_family": task["project_family"],
        "build_system": task["selected_build_system"],
        "phase_facts": phase_facts,
        "progress_facts": progress_facts,
        "semantic_failure_log": semantic_log,
        "candidate_actions": actions,
        "model_input": {
            "state_id": state_id,
            "build_system": task["selected_build_system"],
            "phase_facts": phase_facts,
            "progress_facts": progress_facts,
            "semantic_failure_log": semantic_log,
            "candidate_action_families": list(ACTION_FAMILIES),
        },
    }


def _invalid_build_path(task: dict[str, Any]) -> str:
    return "build/Makefile" if task["selected_build_system"] == "cmake" else "Makefile"


def _fault_trigger_commands(task: dict[str, Any], fault_type: str) -> list[str]:
    invalid = _invalid_build_path(task)
    if fault_type == "missing_compile_input":
        return [
            f"rm -f {shlex.quote(task['fault_file'])}",
            *task["build_commands"],
        ]
    if fault_type == "invalid_build_state":
        return [
            f"printf '%s\\n' all > {shlex.quote(invalid)}",
            *task["build_commands"],
        ]
    if fault_type == "wrong_build_target":
        if task["selected_build_system"] == "cmake":
            return [f"cmake --build build --target {OPAQUE_TARGET} --parallel 4"]
        return [f"make {OPAQUE_TARGET}"]
    if fault_type == "compound_recovery":
        return [
            f"rm -f {shlex.quote(task['fault_file'])}",
            f"printf '%s\\n' all > {shlex.quote(invalid)}",
            *task["build_commands"],
        ]
    raise QualificationError(f"未知 fault type: {fault_type}")


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, symlinks=True)


def _observe(task: dict[str, Any], workspace: Path, artifacts: Path) -> dict[str, Any]:
    invalid = workspace / _invalid_build_path(task)
    artifact_rows = []
    for relative in task["target"]["required_artifacts"]:
        path = artifacts / relative
        artifact_rows.append(
            {
                "path": relative,
                "present": path.is_file(),
                "sha256": v1.file_sha256(path) if path.is_file() else None,
            }
        )
    observation = {
        "fault_input_present": (workspace / task["fault_file"]).is_file(),
        "build_state_present": invalid.is_file(),
        "build_state_sha256": v1.file_sha256(invalid) if invalid.is_file() else None,
        "replay_marker_present": (workspace / MARKER_HEADER).is_file(),
        "artifacts": artifact_rows,
    }
    observation["canonical_sha256"] = v1.canonical_sha256(observation)
    return observation


def _replay_task(task: dict[str, Any], *, include_recovery: bool) -> dict[str, Any]:
    replay = copy.deepcopy(task)
    prefix = list(task["replay_setup_commands"]) if include_recovery else []
    replay["configure_commands"] = [*prefix, *task["replay_configure_commands"]]
    replay["build_commands"] = list(task["replay_build_commands"])
    return replay


def _strict_success(strict: dict[str, Any] | None) -> bool:
    return bool(
        strict is not None
        and strict["exit_code"] == 0
        and not strict["timed_out"]
        and all(
            strict.get("strict_checks", {}).get(name) is True
            for name in ("candidate", "functional", "provenance", "clean_replay")
        )
    )


def _reference_closure(
    *,
    manifest: dict[str, Any],
    image: str,
    task: dict[str, Any],
    configured: Path,
    replicate: int,
    work_root: Path,
    evidence_root: Path,
) -> dict[str, Any]:
    workspace = work_root / "workspace"
    artifacts = work_root / "artifacts"
    _copy_tree(configured, workspace)
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
                v1._oracle_script(task, f"reference-{task['task_id']}-{replicate}"),
            ]
        ),
        log_path=evidence_root / "reference.log",
    )
    if execution["exit_code"] != 0 or execution["timed_out"]:
        raise QualificationError(
            f"{task['task_id']} reference build 失败: {execution['log_tail']}"
        )
    strict_root = work_root / "strict"
    strict_root.mkdir()
    strict = v1._strict_submit(
        manifest=manifest,
        image=image,
        task=task,
        workspace=workspace,
        artifacts=artifacts,
        root=strict_root,
        log_path=evidence_root / "reference-strict.log",
    )
    if not _strict_success(strict):
        raise QualificationError(
            f"{task['task_id']} reference strict closure 失败: {strict['log_tail']}"
        )
    return {
        "task_id": task["task_id"],
        "replicate": replicate,
        "reference_passed": True,
        "build_duration_seconds": execution["duration_seconds"],
        "strict_duration_seconds": strict["duration_seconds"],
        "strict_checks": strict["strict_checks"],
        "artifacts": v1._artifact_evidence(task, artifacts),
    }


def _inject_failure(
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
        script=v1._commands_script(_fault_trigger_commands(task, fault_type)),
        log_path=log_path,
    )
    if result["exit_code"] in (None, 0) or result["timed_out"]:
        raise QualificationError(f"{task['task_id']} {fault_type} 未形成有界构建失败")
    return result


def _prepare_replay_gap(
    *,
    manifest: dict[str, Any],
    image: str,
    task: dict[str, Any],
    source: Path,
    replicate: int,
    work_root: Path,
    evidence_root: Path,
) -> tuple[Path, Path, dict[str, Any]]:
    workspace = work_root / "workspace"
    artifacts = work_root / "artifacts"
    _copy_tree(source, workspace)
    artifacts.mkdir()
    setup = v1._run_container(
        manifest=manifest,
        image=image,
        workspace=workspace,
        artifacts=artifacts,
        script=v1._commands_script(
            [
                *task["replay_setup_commands"],
                *task["replay_configure_commands"],
                *task["replay_build_commands"],
                *task["artifact_stage_commands"],
                v1._oracle_script(task, f"replay-gap-{task['task_id']}-{replicate}"),
            ]
        ),
        log_path=evidence_root / "replay-gap-setup.log",
    )
    if setup["exit_code"] != 0 or setup["timed_out"]:
        raise QualificationError(
            f"{task['task_id']} replay gap workspace 未闭合: {setup['log_tail']}"
        )
    strict_root = work_root / "pre-action-strict"
    strict_root.mkdir()
    strict = v1._strict_submit(
        manifest=manifest,
        image=image,
        task=_replay_task(task, include_recovery=False),
        workspace=workspace,
        artifacts=artifacts,
        root=strict_root,
        log_path=evidence_root / "replay-gap-pre-action-strict.log",
    )
    rejected = (
        not _strict_success(strict) and strict["strict_checks"]["clean_replay"] is False
    )
    if not rejected:
        raise QualificationError(f"{task['task_id']} replay gap 未被 closure 拒绝")
    return (
        workspace,
        artifacts,
        {
            "task_id": task["task_id"],
            "replicate": replicate,
            "rejected": True,
            "setup_duration_seconds": setup["duration_seconds"],
            "strict_duration_seconds": strict["duration_seconds"],
            "strict_checks": strict["strict_checks"],
            "semantic_failure_log": strict["log_tail"],
        },
    )


def _execute_action_branch(
    *,
    manifest: dict[str, Any],
    image: str,
    task: dict[str, Any],
    fault_type: str,
    state: dict[str, Any],
    action: dict[str, Any],
    fault_workspace: Path,
    replicate: int,
    work_root: Path,
    evidence_root: Path,
) -> dict[str, Any]:
    workspace = work_root / "workspace"
    artifacts = work_root / "artifacts"
    _copy_tree(fault_workspace, workspace)
    artifacts.mkdir()
    before = _observe(task, workspace, artifacts)
    action_result = v1._run_container(
        manifest=manifest,
        image=image,
        workspace=workspace,
        artifacts=artifacts,
        script=v1._commands_script(action["bound_commands"]),
        log_path=evidence_root / "action.log",
    )
    action_ok = action_result["exit_code"] == 0 and not action_result["timed_out"]
    continuation: dict[str, Any] | None = None
    strict: dict[str, Any] | None = None
    if action_ok:
        build_commands = (
            task["replay_build_commands"]
            if fault_type == "replay_recipe_gap"
            else task["build_commands"]
        )
        continuation = v1._run_container(
            manifest=manifest,
            image=image,
            workspace=workspace,
            artifacts=artifacts,
            script=v1._commands_script(
                [
                    *build_commands,
                    *task["artifact_stage_commands"],
                    v1._oracle_script(
                        task,
                        f"continuation-{state['state_id']}-{replicate}",
                    ),
                ]
            ),
            log_path=evidence_root / "continuation.log",
        )
        if continuation["exit_code"] == 0 and not continuation["timed_out"]:
            strict_root = work_root / "strict"
            strict_root.mkdir()
            strict_task = task
            if fault_type == "replay_recipe_gap":
                strict_task = _replay_task(
                    task,
                    include_recovery=action["action_family"]
                    in {"dependency", "escalate_agent"},
                )
            strict = v1._strict_submit(
                manifest=manifest,
                image=image,
                task=strict_task,
                workspace=workspace,
                artifacts=artifacts,
                root=strict_root,
                log_path=evidence_root / "strict.log",
            )
    after = _observe(task, workspace, artifacts)
    strict_success = _strict_success(strict)
    continuation_class = (
        "not_run"
        if continuation is None
        else "timeout"
        if continuation["timed_out"]
        else "success"
        if continuation["exit_code"] == 0
        else "failure"
    )
    action_class = (
        "timeout"
        if action_result["timed_out"]
        else "success"
        if action_result["exit_code"] == 0
        else "failure"
    )
    build_executions = int(action["action_family"] == "build")
    build_executions += int(continuation is not None)
    build_executions += int(strict is not None)
    durations = [action_result["duration_seconds"]]
    if continuation is not None:
        durations.append(continuation["duration_seconds"])
    if strict is not None:
        durations.append(strict["duration_seconds"])
    return {
        "state_id": state["state_id"],
        "project_id": task["task_id"],
        "project_family": task["project_family"],
        "build_system": task["selected_build_system"],
        "replicate": replicate,
        "action_family": action["action_family"],
        "action_cost": action["cost"],
        "direct_execution": action["direct_execution"],
        "before_observation": before,
        "after_observation": after,
        "frontier_changed": before["canonical_sha256"] != after["canonical_sha256"],
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
        "strict_exit_code": None if strict is None else strict["exit_code"],
        "strict_timed_out": None if strict is None else strict["timed_out"],
        "strict_duration_seconds": None
        if strict is None
        else strict["duration_seconds"],
        "strict_checks": None if strict is None else strict["strict_checks"],
        "strict_success": strict_success,
        "observed_budget_delta": {
            "wall_clock_milliseconds": round(sum(durations) * 1000),
            "provider_requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "provider_cost_microusd": 0,
            "build_executions": build_executions,
        },
        "replay_signature": {
            "action_family": action["action_family"],
            "action_exit_class": action_class,
            "continuation_exit_class": continuation_class,
            "strict_success": strict_success,
            "strict_failure_class": None
            if strict is None or strict_success
            else next(
                (
                    name
                    for name, passed in strict["strict_checks"].items()
                    if not passed
                ),
                "unknown",
            ),
        },
    }


def _run_project_replicate(
    *,
    manifest: dict[str, Any],
    image: str,
    task: dict[str, Any],
    replicate: int,
    work_root: Path,
    evidence_root: Path,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
    dict[str, str],
]:
    source = work_root / "source"
    configured = work_root / "configured"
    empty_artifacts = work_root / "configured-artifacts"
    v1._clone_exact(task, source)
    source_identity = v1._verify_source(task, source)
    _copy_tree(source, configured)
    empty_artifacts.mkdir()
    configure = v1._run_container(
        manifest=manifest,
        image=image,
        workspace=configured,
        artifacts=empty_artifacts,
        script=v1._commands_script(task["configure_commands"]),
        log_path=evidence_root / "configure.log",
    )
    if configure["exit_code"] != 0 or configure["timed_out"]:
        raise QualificationError(
            f"{task['task_id']} configure checkpoint 失败: {configure['log_tail']}"
        )
    reference_work = work_root / "reference"
    reference_evidence = evidence_root / "reference"
    reference_work.mkdir()
    reference_evidence.mkdir()
    closure = _reference_closure(
        manifest=manifest,
        image=image,
        task=task,
        configured=configured,
        replicate=replicate,
        work_root=reference_work,
        evidence_root=reference_evidence,
    )
    closure["source_identity"] = source_identity

    states: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    hidden: dict[str, str] = {}
    for fault_type in FAULT_TYPES[:-1]:
        fault_work = work_root / f"fault-{FAULT_TYPES.index(fault_type) + 1}"
        fault_evidence = evidence_root / f"fault-{FAULT_TYPES.index(fault_type) + 1}"
        workspace = fault_work / "workspace"
        artifacts = fault_work / "artifacts"
        fault_work.mkdir()
        fault_evidence.mkdir()
        _copy_tree(configured, workspace)
        artifacts.mkdir()
        failure = _inject_failure(
            manifest=manifest,
            image=image,
            task=task,
            fault_type=fault_type,
            workspace=workspace,
            artifacts=artifacts,
            log_path=fault_evidence / "fault.log",
        )
        state = _state_record(task, fault_type, failure["log_tail"])
        states.append(state)
        hidden[state["state_id"]] = fault_type
        for action in state["candidate_actions"]:
            action_work = fault_work / f"action-{action['action_family']}"
            action_evidence = fault_evidence / f"action-{action['action_family']}"
            action_work.mkdir()
            action_evidence.mkdir()
            outcomes.append(
                _execute_action_branch(
                    manifest=manifest,
                    image=image,
                    task=task,
                    fault_type=fault_type,
                    state=state,
                    action=action,
                    fault_workspace=workspace,
                    replicate=replicate,
                    work_root=action_work,
                    evidence_root=action_evidence,
                )
            )

    replay_work = work_root / "fault-5"
    replay_evidence = evidence_root / "fault-5"
    replay_work.mkdir()
    replay_evidence.mkdir()
    replay_workspace, _, precheck = _prepare_replay_gap(
        manifest=manifest,
        image=image,
        task=task,
        source=source,
        replicate=replicate,
        work_root=replay_work,
        evidence_root=replay_evidence,
    )
    replay_state = _state_record(
        task, "replay_recipe_gap", precheck["semantic_failure_log"]
    )
    states.append(replay_state)
    hidden[replay_state["state_id"]] = "replay_recipe_gap"
    for action in replay_state["candidate_actions"]:
        action_work = replay_work / f"action-{action['action_family']}"
        action_evidence = replay_evidence / f"action-{action['action_family']}"
        action_work.mkdir()
        action_evidence.mkdir()
        outcomes.append(
            _execute_action_branch(
                manifest=manifest,
                image=image,
                task=task,
                fault_type="replay_recipe_gap",
                state=replay_state,
                action=action,
                fault_workspace=replay_workspace,
                replicate=replicate,
                work_root=action_work,
                evidence_root=action_evidence,
            )
        )
    return states, outcomes, closure, precheck, hidden


def _derive_action_labels(
    states: list[dict[str, Any]], outcomes: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in outcomes:
        grouped[(row["state_id"], row["action_family"])].append(row)
    labels = []
    consistent = 0
    for state in states:
        safe = []
        for family in ACTION_FAMILIES:
            rows = sorted(
                grouped[(state["state_id"], family)],
                key=lambda item: item["replicate"],
            )
            if len(rows) != 2:
                raise QualificationError(
                    f"{state['state_id']} {family} 缺少两次 branch"
                )
            consistent += int(
                rows[0]["replay_signature"] == rows[1]["replay_signature"]
            )
            if all(row["strict_success"] for row in rows):
                safe.append(family)
        if not safe:
            raise QualificationError(f"{state['state_id']} 没有安全动作")
        optimal = min(safe, key=lambda family: ACTION_COSTS[family])
        labels.append(
            {
                "state_id": state["state_id"],
                "project_family": state["project_family"],
                "build_system": state["build_system"],
                "safe_actions": safe,
                "optimal_action": optimal,
                "optimal_cost": ACTION_COSTS[optimal],
            }
        )
    pair_count = len(states) * len(ACTION_FAMILIES)
    return labels, {
        "state_action_pair_count": pair_count,
        "consistent_state_action_pair_count": consistent,
        "replay_consistency": round(consistent / pair_count, 6),
    }


def _fits(charge: dict[str, int], budget: dict[str, int]) -> bool:
    return all(charge[name] <= budget[name] for name in budget)


def _planned_charge(action: str) -> dict[str, int]:
    return (
        copy.deepcopy(AGENT_RESERVATION)
        if action == "escalate_agent"
        else copy.deepcopy(DIRECT_ROUTE_CHARGES[action])
    )


def _select_route(
    safe_actions: list[str], budget: dict[str, int]
) -> tuple[str, str | None, dict[str, int]]:
    safe_direct = sorted(
        (action for action in safe_actions if action != "escalate_agent"),
        key=lambda action: ACTION_COSTS[action],
    )
    for action in safe_direct:
        charge = _planned_charge(action)
        if _fits(charge, budget):
            return "direct", action, charge
    if "escalate_agent" in safe_actions:
        charge = _planned_charge("escalate_agent")
        if _fits(charge, budget):
            return "escalate_agent", "escalate_agent", charge
    return "stop", None, {name: 0 for name in budget}


def _derive_route_decisions(
    states: list[dict[str, Any]], labels: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    label_by_state = {row["state_id"]: row for row in labels}
    decisions = []
    for state in states:
        label = label_by_state[state["state_id"]]
        for profile, budget in BUDGET_PROFILES.items():
            route, action, charge = _select_route(label["safe_actions"], budget)
            decisions.append(
                {
                    "decision_id": f"{state['state_id']}:{profile}",
                    "state_id": state["state_id"],
                    "project_family": state["project_family"],
                    "build_system": state["build_system"],
                    "budget_profile": profile,
                    "remaining_budget": budget,
                    "optimal_route": route,
                    "optimal_action": action,
                    "planned_charge": charge,
                }
            )
    return decisions


def _route_prediction(action: str, budget: dict[str, int]) -> tuple[str, str | None]:
    charge = _planned_charge(action)
    if not _fits(charge, budget):
        return "stop", None
    if action == "escalate_agent":
        return "escalate_agent", action
    return "direct", action


def _score_route_rows(
    predictions: dict[str, str],
    decisions: list[dict[str, Any]],
    *,
    baseline: str,
) -> dict[str, Any]:
    rows = []
    for decision in decisions:
        state_id = decision["state_id"]
        predicted_action = predictions[state_id]
        route, action = _route_prediction(
            predicted_action, decision["remaining_budget"]
        )
        correct = (
            route == decision["optimal_route"] and action == decision["optimal_action"]
        )
        rows.append(
            {
                "decision_id": decision["decision_id"],
                "state_id": state_id,
                "budget_profile": decision["budget_profile"],
                "predicted_route": route,
                "predicted_action": action,
                "optimal_route": decision["optimal_route"],
                "optimal_action": decision["optimal_action"],
                "correct": correct,
            }
        )
    correct_count = sum(row["correct"] for row in rows)
    return {
        "baseline": baseline,
        "decision_count": len(rows),
        "correct": correct_count,
        "route_accuracy": round(correct_count / len(rows), 6),
        "rows": rows,
    }


def _rule_gate(
    states: list[dict[str, Any]], decisions: list[dict[str, Any]]
) -> dict[str, Any]:
    predictions = {
        state["state_id"]: "dependency"
        if state["phase_facts"]["build_succeeded"] is True
        and state["phase_facts"]["replay_closure_ready"] is False
        else "build"
        for state in states
    }
    return _score_route_rows(predictions, decisions, baseline="phase_budget_rule_gate")


def _tfidf_budgetfit(
    states: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    result = semantic_v2._tfidf_baseline(states, labels)
    predictions = {row["state_id"]: row["prediction"] for row in result["rows"]}
    route = _score_route_rows(predictions, decisions, baseline="log_tfidf_budgetfit")
    route["action_top1_accuracy"] = result["top1_accuracy"]
    route["action_top1_correct"] = result["top1_correct"]
    route["action_rows"] = result["rows"]
    return route


def _leakage_audit(states: list[dict[str, Any]]) -> dict[str, Any]:
    violations = []
    for state in states:
        payload = json.dumps(state["model_input"], ensure_ascii=False).lower()
        for token in FAULT_TYPES:
            if token in payload or token in state["state_id"].lower():
                violations.append({"state_id": state["state_id"], "token": token})
    return {
        "passed": not violations
        and all(
            [row["action_family"] for row in state["candidate_actions"]]
            == list(ACTION_FAMILIES)
            for state in states
        ),
        "violations": violations,
        "hidden_fault_field_in_model_input": False,
    }


def analyse_results(
    manifest: dict[str, Any],
    states: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    references: list[dict[str, Any]],
    replay_prechecks: list[dict[str, Any]],
) -> dict[str, Any]:
    labels, replay = _derive_action_labels(states, outcomes)
    decisions = _derive_route_decisions(states, labels)
    rule = _rule_gate(states, decisions)
    tfidf = _tfidf_budgetfit(states, labels, decisions)
    leakage = _leakage_audit(states)
    routes_by_system = {
        system: {
            row["optimal_route"] for row in decisions if row["build_system"] == system
        }
        for system in BUILD_SYSTEMS
    }
    actions_by_system = {
        system: {
            row["optimal_action"] for row in labels if row["build_system"] == system
        }
        for system in BUILD_SYSTEMS
    }
    routes_per_state: dict[str, set[str]] = defaultdict(set)
    for row in decisions:
        routes_per_state[row["state_id"]].add(row["optimal_route"])
    replay_state_ids = (
        {
            state_id
            for state_id, fault in manifest_runtime_hidden_mapping.items()
            if fault == "replay_recipe_gap"
        }
        if manifest_runtime_hidden_mapping
        else {
            state["state_id"]
            for state in states
            if state["phase_facts"]["build_succeeded"] is True
        }
    )
    replay_dependency = [
        row
        for row in outcomes
        if row["state_id"] in replay_state_ids
        and row["action_family"] == "dependency"
        and row["strict_success"]
    ]
    thresholds = manifest["thresholds"]
    expected_budget_keys = set(next(iter(BUDGET_PROFILES.values())))
    gates = {
        "expected_counts": len(states) == 30
        and len(outcomes) == 240
        and len(references) == 12
        and len(replay_prechecks) == 12
        and len(decisions) == 90,
        "reference_closure": all(
            row["reference_passed"] and all(row["strict_checks"].values())
            for row in references
        ),
        "replay_consistency": replay["replay_consistency"]
        >= thresholds["minimum_replay_consistency"],
        "cross_system_action_and_route_support": all(
            actions_by_system[system] == set(ACTION_FAMILIES)
            and routes_by_system[system] == {"direct", "escalate_agent", "stop"}
            for system in BUILD_SYSTEMS
        ),
        "rule_gate_below_ceiling": rule["route_accuracy"]
        < thresholds["maximum_rule_gate_route_accuracy_exclusive"],
        "tfidf_budgetfit_below_ceiling": tfidf["route_accuracy"]
        < thresholds["maximum_tfidf_budgetfit_route_accuracy_exclusive"],
        "matched_budget_changes_route": sum(
            len(routes) >= 2 for routes in routes_per_state.values()
        )
        >= thresholds["minimum_states_with_budget_route_change"],
        "replay_rejection_and_recovery": sum(
            row["rejected"] for row in replay_prechecks
        )
        == thresholds["required_replay_rejections"]
        and len(replay_dependency)
        == thresholds["required_replay_dependency_recoveries"],
        "no_direct_label_leakage": leakage["passed"],
        "bounded_execution": all(
            row["action_timed_out"] is False
            and row["action_exit_code"] is not None
            and row["continuation_timed_out"] is not True
            and row["strict_timed_out"] is not True
            for row in outcomes
        ),
        "budget_and_observation_closure": all(
            set(row["observed_budget_delta"]) == expected_budget_keys
            and row["observed_budget_delta"]["provider_requests"] == 0
            and row["before_observation"]["canonical_sha256"]
            == v1.canonical_sha256(
                {
                    key: value
                    for key, value in row["before_observation"].items()
                    if key != "canonical_sha256"
                }
            )
            and row["after_observation"]["canonical_sha256"]
            == v1.canonical_sha256(
                {
                    key: value
                    for key, value in row["after_observation"].items()
                    if key != "canonical_sha256"
                }
            )
            for row in outcomes
        ),
        "zero_provider_boundary": all(
            row["observed_budget_delta"][name] == 0
            for row in outcomes
            for name in (
                "provider_requests",
                "input_tokens",
                "output_tokens",
                "provider_cost_microusd",
            )
        ),
        "cleanup": True,
    }
    passed = all(gates.values())
    return {
        "counts": {
            "project_count": len({state["project_family"] for state in states}),
            "state_count": len(states),
            "action_branch_count": len(outcomes),
            "reference_closure_count": len(references),
            "replay_precheck_count": len(replay_prechecks),
            "budget_decision_count": len(decisions),
            "optimal_actions": dict(
                sorted(Counter(row["optimal_action"] for row in labels).items())
            ),
            "optimal_routes": dict(
                sorted(Counter(row["optimal_route"] for row in decisions).items())
            ),
            "states_with_budget_route_change": sum(
                len(routes) >= 2 for routes in routes_per_state.values()
            ),
            "replay_dependency_recoveries": len(replay_dependency),
        },
        "action_labels": labels,
        "budget_decisions": decisions,
        "replay": replay,
        "rule_gate": rule,
        "tfidf_budgetfit": tfidf,
        "leakage_audit": leakage,
        "gates": gates,
        "passed": passed,
        "decision": manifest["decision_rule"]["pass"]
        if passed
        else manifest["decision_rule"]["fail"],
        "thresholds_adjusted_after_results": False,
        "provider_calls": 0,
        "credential_reads": 0,
        "jev_calls": 0,
        "agent_calls": 0,
        "model_tokens": 0,
    }


manifest_runtime_hidden_mapping: dict[str, str] = {}


def _write_once(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        payload
        if isinstance(payload, str)
        else json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text)


def _inventory(root: Path) -> dict[str, Any]:
    excluded = {"inventory.json", "completed.json"}
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        rows.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": v1.file_sha256(path),
            }
        )
    return {
        "files": rows,
        "file_count": len(rows),
        "total_bytes": sum(row["size_bytes"] for row in rows),
        "canonical_sha256": v1.canonical_sha256(rows),
    }


def run_qualification(manifest: dict[str, Any], pool: dict[str, Any]) -> dict[str, Any]:
    readiness = preflight(manifest, pool)
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=False)
    _write_once(
        EVIDENCE_ROOT / "attempt.json",
        {
            "identity": IDENTITY,
            "attempt": 1,
            "started_at": datetime.now(UTC).isoformat(),
            "git_commit": readiness["git_commit"],
            "manifest_canonical_sha256": v1.canonical_sha256(manifest),
            "authorization": manifest["authorization"],
        },
    )
    states_by_id: dict[str, dict[str, Any]] = {}
    outcomes: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    replay_prechecks: list[dict[str, Any]] = []
    hidden: dict[str, str] = {}
    try:
        with tempfile.TemporaryDirectory(prefix="forge-progress-budget-jev-v1-") as tmp:
            work = Path(tmp)
            for task in pool["tasks"]:
                for replicate in range(1, manifest["environment"]["replicates"] + 1):
                    work_root = work / f"{task['task_id']}-r{replicate}"
                    evidence_root = (
                        EVIDENCE_ROOT / "runs" / task["task_id"] / f"r{replicate}"
                    )
                    work_root.mkdir()
                    evidence_root.mkdir(parents=True)
                    project_states, project_outcomes, closure, precheck, mapping = (
                        _run_project_replicate(
                            manifest=manifest,
                            image=readiness["image_id"],
                            task=task,
                            replicate=replicate,
                            work_root=work_root,
                            evidence_root=evidence_root,
                        )
                    )
                    if replicate == 1:
                        for state in project_states:
                            states_by_id[state["state_id"]] = state
                        hidden.update(mapping)
                    else:
                        if {row["state_id"] for row in project_states} != {
                            row["state_id"]
                            for row in states_by_id.values()
                            if row["project_family"] == task["project_family"]
                        }:
                            raise QualificationError("replicate state identity 漂移")
                    outcomes.extend(project_outcomes)
                    references.append(closure)
                    replay_prechecks.append(precheck)
        states = sorted(states_by_id.values(), key=lambda row: row["state_id"])
        outcomes.sort(
            key=lambda row: (
                row["state_id"],
                row["action_family"],
                row["replicate"],
            )
        )
        global manifest_runtime_hidden_mapping
        manifest_runtime_hidden_mapping = dict(hidden)
        analysis = analyse_results(
            manifest, states, outcomes, references, replay_prechecks
        )
        raw = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "document_type": "forge_progress_budget_jev_identifiability_qualification_report",
            "identity": IDENTITY,
            "issue_url": ISSUE_URL,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "completed",
            "git_branch": readiness["git_branch"],
            "git_commit": readiness["git_commit"],
            "image_id": readiness["image_id"],
            "manifest_canonical_sha256": v1.canonical_sha256(manifest),
            "source_pool_canonical_sha256": v1.canonical_sha256(pool),
            "states": states,
            "hidden_fault_mapping": dict(sorted(hidden.items())),
            "outcomes": outcomes,
            "reference_closures": references,
            "replay_prechecks": replay_prechecks,
            "analysis": analysis,
            "interpretation": {
                "benchmark_identifiability_estimated": True,
                "jev_effect_estimated": False,
                "agent_effect_estimated": False,
                "controller_effect_estimated": False,
                "agent_reservation_is_actual_usage": False,
                "historical_evidence_modified": False,
            },
        }
        validate_report(raw, manifest, pool)
        _write_once(EVIDENCE_ROOT / "result.json", raw)
        inventory = _inventory(EVIDENCE_ROOT)
        _write_once(EVIDENCE_ROOT / "inventory.json", inventory)
        completed = {
            "identity": IDENTITY,
            "status": "completed",
            "decision": analysis["decision"],
            "completed_at": datetime.now(UTC).isoformat(),
            "inventory_canonical_sha256": inventory["canonical_sha256"],
            "zero_managed_resources": True,
        }
        v1.require_zero_managed_resources()
        _write_once(EVIDENCE_ROOT / "completed.json", completed)
        report = copy.deepcopy(raw)
        report["evidence"] = {
            "root": EVIDENCE_ROOT.relative_to(REPO_ROOT).as_posix(),
            "inventory_canonical_sha256": inventory["canonical_sha256"],
            "file_count": inventory["file_count"],
            "total_bytes": inventory["total_bytes"],
            "zero_managed_resources": True,
        }
        v1.write_once(
            DEFAULT_JSON_REPORT,
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        v1.write_once(DEFAULT_MARKDOWN_REPORT, render_markdown(report))
        return report
    except Exception as exc:
        _write_once(
            EVIDENCE_ROOT / "failure.json",
            {
                "identity": IDENTITY,
                "status": "attempt_failed",
                "failed_at": datetime.now(UTC).isoformat(),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "retry_authorized": False,
            },
        )
        raise
    finally:
        v1.require_zero_managed_resources()


def validate_report(
    report: dict[str, Any], manifest: dict[str, Any], pool: dict[str, Any]
) -> dict[str, Any]:
    validate_manifest(manifest, pool)
    if (
        report.get("schema_version") != REPORT_SCHEMA_VERSION
        or report.get("identity") != IDENTITY
        or report.get("status") != "completed"
    ):
        raise QualificationError("report identity 或终态无效")
    if report["manifest_canonical_sha256"] != v1.canonical_sha256(manifest):
        raise QualificationError("report manifest hash 漂移")
    if report["source_pool_canonical_sha256"] != v1.canonical_sha256(pool):
        raise QualificationError("report source pool hash 漂移")
    mapping = report.get("hidden_fault_mapping", {})
    if Counter(mapping.values()) != {fault: 6 for fault in FAULT_TYPES}:
        raise QualificationError("hidden fault mapping 配额漂移")
    global manifest_runtime_hidden_mapping
    manifest_runtime_hidden_mapping = dict(mapping)
    regenerated = analyse_results(
        manifest,
        report["states"],
        report["outcomes"],
        report["reference_closures"],
        report["replay_prechecks"],
    )
    if report["analysis"] != regenerated:
        raise QualificationError("report 无法从 raw outcome 重建")
    return report


def audit_evidence(manifest: dict[str, Any], pool: dict[str, Any]) -> dict[str, Any]:
    marker = v1.load_json(EVIDENCE_ROOT / "completed.json")
    inventory = v1.load_json(EVIDENCE_ROOT / "inventory.json")
    raw = v1.load_json(EVIDENCE_ROOT / "result.json")
    report = validate_report(v1.load_json(DEFAULT_JSON_REPORT), manifest, pool)
    validate_report(raw, manifest, pool)
    observed = _inventory(EVIDENCE_ROOT)
    valid = (
        marker["status"] == "completed"
        and marker["decision"] == raw["analysis"]["decision"]
        and marker["inventory_canonical_sha256"]
        == inventory["canonical_sha256"]
        == observed["canonical_sha256"]
        and inventory == observed
        and report["analysis"] == raw["analysis"]
    )
    v1.require_zero_managed_resources()
    return {
        "valid": valid,
        "identity": IDENTITY,
        "decision": raw["analysis"]["decision"],
        "inventory_canonical_sha256": observed["canonical_sha256"],
        "file_count": observed["file_count"],
        "total_bytes": observed["total_bytes"],
        "zero_managed_resources": True,
    }


def render_markdown(report: dict[str, Any]) -> str:
    analysis = report["analysis"]
    failed = [name for name in GATE_ORDER if not analysis["gates"][name]]
    conclusion = (
        "联合 benchmark 通过可辨识性资格，允许进入独立 Jev 进展预算校准设计；尚未授权 Provider 或完整 controller。"
        if analysis["passed"]
        else "联合 benchmark 未通过可辨识性资格，停止 Jev calibration 和 controller 实现。失败门槛："
        + ", ".join(failed)
        + "。"
    )
    gates = "\n".join(
        f"| `{name}` | {'通过' if analysis['gates'][name] else '失败'} |"
        for name in GATE_ORDER
    )
    actions = "\n".join(
        f"| `{name}` | {analysis['counts']['optimal_actions'].get(name, 0)} |"
        for name in ACTION_FAMILIES
    )
    routes = "\n".join(
        f"| `{name}` | {analysis['counts']['optimal_routes'].get(name, 0)} |"
        for name in ("direct", "escalate_agent", "stop")
    )
    return f"""# 进展预算感知 Jev 联合 benchmark 可辨识性资格 v1 结果

- Identity：`{IDENTITY}`；
- Tracking Issue：[#457]({ISSUE_URL})；
- 执行 revision：`{report["git_commit"]}`；
- 决定：`{analysis["decision"]}`。

## 关键结论

{conclusion}

本阶段在 6 个未见项目族上真实执行五类状态、四类动作和三种 matched budget。标签来自两次 action branch 的严格结果与冻结预算可行性，不使用人工期望或旧 Agent 行为。

## 结果

- 项目：`{analysis["counts"]["project_count"]}`；
- 语义状态：`{analysis["counts"]["state_count"]}`；
- action branches：`{analysis["counts"]["action_branch_count"]}`；
- matched budget decisions：`{analysis["counts"]["budget_decision_count"]}`；
- action replay 一致率：`{analysis["replay"]["replay_consistency"]:.4f}`；
- RuleGate route accuracy：`{analysis["rule_gate"]["route_accuracy"]:.4f}`；
- TF-IDF+BudgetFit action top-1：`{analysis["tfidf_budgetfit"]["action_top1_accuracy"]:.4f}`；
- TF-IDF+BudgetFit route accuracy：`{analysis["tfidf_budgetfit"]["route_accuracy"]:.4f}`；
- 发生预算路由变化的状态：`{analysis["counts"]["states_with_budget_route_change"]}/30`；
- replay dependency recoveries：`{analysis["counts"]["replay_dependency_recoveries"]}/12`。

| 最优动作 | 状态数 |
|---|---:|
{actions}

| 最优路由 | decision 数 |
|---|---:|
{routes}

| 门槛 | 结果 |
|---|---|
{gates}

## 解释边界

本结果只评价 benchmark 的联合可辨识性。它不估计 Jev、真实 Agent 或 controller 效果，不支持成功率非劣、Provider 成本下降、自然失败或开放世界结论。Agent reservation 是冻结规划量，实际 credential、Provider、Jev、Agent 和 model token 均为 0；历史 evidence 未修改。

## Evidence

- Root：`{report["evidence"]["root"]}`；
- Inventory：`{report["evidence"]["file_count"]}` files / `{report["evidence"]["total_bytes"]}` bytes；
- Inventory canonical SHA-256：`{report["evidence"]["inventory_canonical_sha256"]}`；
- Cleanup：`0` managed resource。
"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("generate")
    subparsers.add_parser("validate")
    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--allow-dirty", action="store_true")
    subparsers.add_parser("run")
    subparsers.add_parser("audit")
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
                preflight(manifest, pool, require_clean=not args.allow_dirty),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "run":
        report = run_qualification(manifest, pool)
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
    if args.command == "audit":
        print(json.dumps(audit_evidence(manifest, pool), ensure_ascii=False, indent=2))
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

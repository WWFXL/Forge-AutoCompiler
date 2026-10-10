#!/usr/bin/env python3
"""Issue #408 Jev 未见项目族正式三臂比较 v5。"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import logging
import math
import os
import random
import re
import shlex
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
for import_root in (str(SCRIPT_PATH.parent), str(BACKEND_ROOT / "packages/harness")):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_agent_workflow_stage_b_phase5_v2_authorized_runner as agent_runner  # noqa: E402
import forge_jev_offline_qualification_candidate as jev_candidate  # noqa: E402
import forge_jev_offline_qualification_v6 as jev_v6  # noqa: E402
import forge_typed_semantic_routing_pilot_v2 as semantic_v2  # noqa: E402
from deerflow.compile.agent_workflow_node import (  # noqa: E402
    AgentWorkflowBudgetTracker,
    AgentWorkflowCandidateStore,
    AgentWorkflowNodeStatus,
    AgentWorkflowStateMachine,
)
from deerflow.compile.agent_workflow_runtime import (  # noqa: E402
    AgentWorkflowCandidateService,
    AgentWorkflowEvidenceLedger,
    run_agent_workflow_node_v1,
)
from deerflow.compile.agent_workflow_schemas import (  # noqa: E402
    AgentBuildNodeInput,
    AgentBuildNodeResult,
    AgentWorkflowBudget,
    AgentWorkflowEnvironmentIdentity,
    AgentWorkflowExperimentIdentity,
    AgentWorkflowTargetContract,
    AgentWorkflowUsage,
    SubmitCandidateRequest,
)
from deerflow.compile.evidence import (  # noqa: E402
    ExperimentLedger,
    ExperimentPolicy,
    activate_experiment,
    deactivate_experiment,
    new_evidence_id,
)
from deerflow.compile.external_evaluator_v2 import (  # noqa: E402
    ForgeCompileEvaluationBackend,
    FunctionalOracleSpec,
    run_external_evaluator_v2,
)
from deerflow.compile.jev_controller import (  # noqa: E402
    CalibrationContract,
    CandidateAction,
    DecisionState,
    TypedDecision,
    VerifierCapabilities,
    dispatch_route,
    route_next_action,
)
from deerflow.compile.operations import (  # noqa: E402
    cleanup_and_finalize_compile_session_impl,
    clone_repository_impl,
    get_compile_services,
    inspect_build_system_impl,
    prepare_compile_session_impl,
)
from deerflow.compile.paths import (  # noqa: E402
    get_compile_sessions_root,
    get_host_compile_sessions_root,
)
from deerflow.tools.bound_compile_tools import _run_container_bash_impl  # noqa: E402
from deerflow.tools.builtins.agent_compile_tools import (  # noqa: E402
    _enforce_experiment_build_system,
)
from typesafe_sdk import RetryPolicy, TypeSafeClient  # noqa: E402

IDENTITY = "cpp-jev-formal-comparison-v5"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/408"
BRANCH = "yiwei/408-jev-formal-comparison"
SCHEMA_VERSION = "forge-jev-formal-comparison-5.0.0"
REPORT_SCHEMA_VERSION = "forge-jev-formal-comparison-report-5.0.0"

MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/cpp-jev-formal-comparison-v5.json"
SCHEMA_PATH = (
    REPO_ROOT / "benchmarks/schemas/forge-jev-formal-comparison-v5.schema.json"
)
PREREGISTRATION_PATH = (
    REPO_ROOT / "benchmarks/preregistrations/cpp-jev-formal-comparison-v5.md"
)
QUALIFICATION_JSON_PATH = (
    REPO_ROOT / "benchmarks/reports/cpp-jev-formal-comparison-v5-qualification.json"
)
QUALIFICATION_MARKDOWN_PATH = (
    REPO_ROOT / "benchmarks/reports/cpp-jev-formal-comparison-v5-qualification.md"
)
JSON_REPORT_PATH = REPO_ROOT / "benchmarks/reports/cpp-jev-formal-comparison-v5.json"
MARKDOWN_REPORT_PATH = REPO_ROOT / "benchmarks/reports/cpp-jev-formal-comparison-v5.md"
EVIDENCE_ROOT = (
    REPO_ROOT / ".compile-sessions/benchmark-evidence-jev-formal-comparison-v5"
)
CREDENTIAL_FILE = REPO_ROOT / "jev-apikey.txt"

CANARY_V7_MANIFEST_PATH = (
    REPO_ROOT / "benchmarks/manifests/cpp-jev-end-to-end-canary-v7.json"
)
CANARY_V7_QUALIFICATION_PATH = (
    REPO_ROOT / "benchmarks/reports/cpp-jev-end-to-end-canary-v7-qualification.json"
)
CANARY_V7_REPORT_PATH = (
    REPO_ROOT / "benchmarks/reports/cpp-jev-end-to-end-canary-v7.json"
)
V1_QUALIFICATION_FAILURE_PATH = (
    REPO_ROOT
    / "benchmarks/reports/cpp-jev-formal-comparison-v1-qualification-failure.json"
)
V2_QUALIFICATION_FAILURE_PATH = (
    REPO_ROOT
    / "benchmarks/reports/cpp-jev-formal-comparison-v2-qualification-failure.json"
)
V3_QUALIFICATION_FAILURE_PATH = (
    REPO_ROOT
    / "benchmarks/reports/cpp-jev-formal-comparison-v3-qualification-failure.json"
)
V4_QUALIFICATION_PATH = (
    REPO_ROOT / "benchmarks/reports/cpp-jev-formal-comparison-v4-qualification.json"
)
V4_QUALIFICATION_FAILURE_PATH = (
    REPO_ROOT
    / "benchmarks/reports/cpp-jev-formal-comparison-v4-qualification-failure.json"
)
PARENT_PATHS = (
    CANARY_V7_MANIFEST_PATH,
    CANARY_V7_QUALIFICATION_PATH,
    CANARY_V7_REPORT_PATH,
    V1_QUALIFICATION_FAILURE_PATH,
    V2_QUALIFICATION_FAILURE_PATH,
    V3_QUALIFICATION_FAILURE_PATH,
    V4_QUALIFICATION_PATH,
    V4_QUALIFICATION_FAILURE_PATH,
)

COMPILE_IMAGE = "autocompiler:gcc13"
EXPECTED_IMAGE_ID = (
    "sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a"
)
AGENT_PROFILE = "deepseek-flash"
AGENT_ENDPOINT = "https://api.deepseek.com"
AGENT_CREDENTIAL_ENV = "DEEPSEEK_API_KEY"
AGENT_REQUEST_TIMEOUT_SECONDS = 300
AGENT_MAX_RETRIES = 0
# 2026-10-11 DeepSeek 官方价目表的 peak/cache-miss 上界；不使用 cache 折扣。
AGENT_INPUT_PRICE_USD_PER_MILLION_TOKENS = 0.30
AGENT_OUTPUT_PRICE_USD_PER_MILLION_TOKENS = 1.20
AGENT_PRICING_SOURCE = "https://api-docs.deepseek.com/quick_start/pricing"

ARMS = ("always_agent", "rule_gate_agent", "jev_gate_agent")
EVALUATION_CUTOFF = "2026-10-08T20:06:00Z"
REPETITIONS = 2
NONINFERIORITY_MARGIN = -0.10
MINIMUM_COST_REDUCTION = 0.20
BOOTSTRAP_SEED = 40820261011
BOOTSTRAP_SAMPLES = 20_000


def _formal_task(
    *,
    task_id: str,
    repository_url: str,
    commit_sha: str,
    source_snapshot_sha256: str,
    build_system: str,
    fault_file: str,
    configure_commands: list[str],
    configure_repair_commands: list[str],
    build_commands: list[str],
    artifact_stage_commands: list[str],
    required_artifacts: list[str],
    artifact_types: list[str],
    oracle: dict[str, Any],
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "project_family": repository_url.removesuffix(".git").lower(),
        "repository_url": repository_url,
        "commit_sha": commit_sha,
        "source_snapshot_sha256": source_snapshot_sha256,
        "selected_build_system": build_system,
        "fault_file": fault_file,
        "configure_commands": configure_commands,
        "configure_repair_commands": configure_repair_commands,
        "build_commands": build_commands,
        "artifact_stage_commands": artifact_stage_commands,
        "target": {
            "required_artifacts": required_artifacts,
            "artifact_types": artifact_types,
            "bitwise_required": "executable" not in artifact_types,
        },
        "oracle": oracle,
    }


TASKS = (
    _formal_task(
        task_id="libgit2",
        repository_url="https://github.com/libgit2/libgit2",
        commit_sha="1484ddee27a0f85c3d3303ccc432fb22f6fca8fd",
        source_snapshot_sha256="cb982bf44dab59448ca593a5b75c57a6a8106af0a5b95a88e6eac8d036bf6afc",
        build_system="cmake",
        fault_file="include/git2.h",
        configure_commands=[
            "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DBUILD_TESTS=OFF -DBUILD_CLI=OFF -DUSE_SSH=OFF -DUSE_HTTPS=OFF -DUSE_AUTH_NTLM=OFF"
        ],
        configure_repair_commands=[
            "rm -rf build",
            "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DBUILD_TESTS=OFF -DBUILD_CLI=OFF -DUSE_SSH=OFF -DUSE_HTTPS=OFF -DUSE_AUTH_NTLM=OFF",
        ],
        build_commands=["cmake --build build --parallel 4"],
        artifact_stage_commands=[
            "mkdir -p /artifacts/lib /artifacts/include && cp build/libgit2.a /artifacts/lib/ && cp -r include/git2 /artifacts/include/ && cp include/git2.h /artifacts/include/"
        ],
        required_artifacts=["include/git2.h", "lib/libgit2.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <git2.h>\nint main(void){int a,b,c;git_libgit2_version(&a,&b,&c);return a<1;}\n",
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libgit2.a",
                "-lpthread",
                "-ldl",
                "-lz",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
    ),
    _formal_task(
        task_id="simdjson",
        repository_url="https://github.com/simdjson/simdjson",
        commit_sha="7f6f8dca84c3c9129b8a4506d55a4ae1c16024f0",
        source_snapshot_sha256="21505e8faf3a77d23fd01f56b6856b57c8b879d11d8fd5126028193683857f76",
        build_system="cmake",
        fault_file="src/simdjson.cpp",
        configure_commands=[
            "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DSIMDJSON_DEVELOPER_MODE=OFF -DBUILD_SHARED_LIBS=OFF"
        ],
        configure_repair_commands=[
            "rm -rf build",
            "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DSIMDJSON_DEVELOPER_MODE=OFF -DBUILD_SHARED_LIBS=OFF",
        ],
        build_commands=["cmake --build build --target simdjson --parallel 4"],
        artifact_stage_commands=[
            "mkdir -p /artifacts/lib /artifacts/include && cp build/libsimdjson.a /artifacts/lib/ && cp -r include/simdjson.h include/simdjson /artifacts/include/"
        ],
        required_artifacts=["include/simdjson.h", "lib/libsimdjson.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c++17",
            "source": "#include <simdjson.h>\nint main(){return simdjson::get_active_implementation()->name().empty();}\n",
            "compile_argv": [
                "c++",
                "-std=c++17",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libsimdjson.a",
                "-pthread",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
    ),
    _formal_task(
        task_id="benchmark",
        repository_url="https://github.com/google/benchmark",
        commit_sha="f2f78087c2235e9e3156d0651be26660005a03a1",
        source_snapshot_sha256="21bc68005a6e8f236b5cbb8899a14ddff6412ef5d88e52a65c98b1210bb3cbfe",
        build_system="cmake",
        fault_file="src/benchmark.cc",
        configure_commands=[
            "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DBENCHMARK_ENABLE_TESTING=OFF -DBENCHMARK_ENABLE_INSTALL=OFF -DBENCHMARK_ENABLE_GTEST_TESTS=OFF"
        ],
        configure_repair_commands=[
            "rm -rf build",
            "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DBENCHMARK_ENABLE_TESTING=OFF -DBENCHMARK_ENABLE_INSTALL=OFF -DBENCHMARK_ENABLE_GTEST_TESTS=OFF",
        ],
        build_commands=["cmake --build build --target benchmark --parallel 4"],
        artifact_stage_commands=[
            "mkdir -p /artifacts/lib /artifacts/include && cp build/src/libbenchmark.a /artifacts/lib/ && cp -r include/benchmark /artifacts/include/"
        ],
        required_artifacts=["include/benchmark/benchmark.h", "lib/libbenchmark.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c++17",
            "source": "#include <benchmark/benchmark.h>\nint main(){return benchmark::CPUInfo::Get().num_cpus>0?0:1;}\n",
            "compile_argv": [
                "c++",
                "-std=c++17",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libbenchmark.a",
                "-pthread",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
    ),
    _formal_task(
        task_id="pcre2",
        repository_url="https://github.com/PCRE2Project/pcre2",
        commit_sha="ead0e18635bd70e321354531d0c2fb38b928853d",
        source_snapshot_sha256="1726e5955c70c9bee5dc96b2854de14640faa85eac14764f29cff2082c8252d5",
        build_system="cmake",
        fault_file="src/pcre2_compile.c",
        configure_commands=[
            "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DPCRE2_BUILD_PCRE2GREP=ON -DPCRE2_BUILD_TESTS=OFF"
        ],
        configure_repair_commands=[
            "rm -rf build",
            "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DPCRE2_BUILD_PCRE2GREP=ON -DPCRE2_BUILD_TESTS=OFF",
        ],
        build_commands=["cmake --build build --target pcre2grep --parallel 4"],
        artifact_stage_commands=["cp build/pcre2grep /artifacts/pcre2grep"],
        required_artifacts=["pcre2grep"],
        artifact_types=["executable"],
        oracle={"kind": "command", "argv": ["/artifacts/pcre2grep", "--version"]},
    ),
    _formal_task(
        task_id="haproxy",
        repository_url="https://github.com/haproxy/haproxy",
        commit_sha="a8639b910f3bfbfd21456ea35811ec83d5c4d867",
        source_snapshot_sha256="6dce2f50ee05237d6eb3a7eca6963209ed9f995292dadb055d1e78b6d3e44dd0",
        build_system="make",
        fault_file="src/haproxy.c",
        configure_commands=["test -f Makefile"],
        configure_repair_commands=["git checkout HEAD -- Makefile", "test -f Makefile"],
        build_commands=[
            "make -j4 TARGET=linux-glibc USE_OPENSSL= USE_ZLIB= USE_PCRE= haproxy"
        ],
        artifact_stage_commands=["cp haproxy /artifacts/haproxy"],
        required_artifacts=["haproxy"],
        artifact_types=["executable"],
        oracle={"kind": "command", "argv": ["/artifacts/haproxy", "-v"]},
    ),
    _formal_task(
        task_id="cc65",
        repository_url="https://github.com/cc65/cc65",
        commit_sha="b3bf30f090f091a111fb3a19de0df44b2a7cf530",
        source_snapshot_sha256="4ae1fb267a71dfe3b357f6fd34cfdd1ea2965267b91340f257fa7aad25ad11c9",
        build_system="make",
        fault_file="src/cc65/main.c",
        configure_commands=["test -f Makefile"],
        configure_repair_commands=["git checkout HEAD -- Makefile", "test -f Makefile"],
        build_commands=["make -j4"],
        artifact_stage_commands=["cp bin/cc65 /artifacts/cc65"],
        required_artifacts=["cc65"],
        artifact_types=["executable"],
        oracle={"kind": "command", "argv": ["/artifacts/cc65", "--version"]},
    ),
    _formal_task(
        task_id="quickjs",
        repository_url="https://github.com/bellard/quickjs",
        commit_sha="9d01a96849dbbe653da65f231cd40bddc7457ae2",
        source_snapshot_sha256="320a80d616dede86413c8aecc46d665e971f0bf55eec414599d795917c537def",
        build_system="make",
        fault_file="quickjs.c",
        configure_commands=["test -f Makefile"],
        configure_repair_commands=[
            "git checkout HEAD -- Makefile",
            "test -f Makefile",
        ],
        build_commands=["make -j4 qjs"],
        artifact_stage_commands=["cp qjs /artifacts/qjs"],
        required_artifacts=["qjs"],
        artifact_types=["executable"],
        oracle={
            "kind": "command",
            "argv": [
                "/artifacts/qjs",
                "-e",
                "if (6 * 7 !== 42) throw new Error('bad')",
            ],
        },
    ),
    _formal_task(
        task_id="redis",
        repository_url="https://github.com/redis/redis",
        commit_sha="558ef8fafb508adb276fb838442f7f202fc1d7e6",
        source_snapshot_sha256="ffd15bd570f568e25f6a5f44197aab9f4b5a7104ff7a5a60a1ae9fb01275c966",
        build_system="make",
        fault_file="src/server.c",
        configure_commands=["test -f Makefile"],
        configure_repair_commands=["git checkout HEAD -- Makefile", "test -f Makefile"],
        build_commands=[
            "SOURCE_DATE_EPOCH=1791622465 make -j4 BUILD_TLS=no MALLOC=libc redis-server"
        ],
        artifact_stage_commands=["cp src/redis-server /artifacts/redis-server"],
        required_artifacts=["redis-server"],
        artifact_types=["executable"],
        oracle={"kind": "command", "argv": ["/artifacts/redis-server", "--version"]},
    ),
    _formal_task(
        task_id="libarchive",
        repository_url="https://github.com/libarchive/libarchive",
        commit_sha="4e97bd559929642d827020b7dffa1fe7483af5e6",
        source_snapshot_sha256="de8029ef74dd99628f1c8d47b085d89f60a9b2269bbe191f091601c982c7e08f",
        build_system="autotools",
        fault_file="libarchive/archive_read.c",
        configure_commands=[
            "autoreconf -fi",
            "./configure --disable-shared --enable-static --without-xml2 --without-expat --without-openssl --without-lz4 --without-zstd --without-lzma --without-bz2lib --without-libb2 --without-iconv --without-zlib",
        ],
        configure_repair_commands=[
            "autoreconf -fi",
            "./configure --disable-shared --enable-static --without-xml2 --without-expat --without-openssl --without-lz4 --without-zstd --without-lzma --without-bz2lib --without-libb2 --without-iconv --without-zlib",
        ],
        build_commands=["make -j4 libarchive.la"],
        artifact_stage_commands=[
            "mkdir -p /artifacts/lib /artifacts/include && cp .libs/libarchive.a /artifacts/lib/ && cp libarchive/archive.h libarchive/archive_entry.h /artifacts/include/"
        ],
        required_artifacts=["include/archive.h", "lib/libarchive.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <archive.h>\nint main(void){return archive_version_number()>0?0:1;}\n",
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libarchive.a",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
    ),
    _formal_task(
        task_id="curl",
        repository_url="https://github.com/curl/curl",
        commit_sha="82aea8c0675c108a1f656e3a33c7fda09ba7aa50",
        source_snapshot_sha256="5d31ac6a6875606c5d9b9d2d46e623ff7b96e66ec1cc606c46ebbfa1d8622bb5",
        build_system="autotools",
        fault_file="lib/easy.c",
        configure_commands=[
            "autoreconf -fi",
            "./configure --disable-shared --enable-static --without-ssl --without-libpsl --without-zlib --without-brotli --without-zstd --disable-ldap --disable-ldaps --disable-docs",
        ],
        configure_repair_commands=[
            "autoreconf -fi",
            "./configure --disable-shared --enable-static --without-ssl --without-libpsl --without-zlib --without-brotli --without-zstd --disable-ldap --disable-ldaps --disable-docs",
        ],
        build_commands=["make -j4"],
        artifact_stage_commands=["cp src/curl /artifacts/curl"],
        required_artifacts=["curl"],
        artifact_types=["executable"],
        oracle={"kind": "command", "argv": ["/artifacts/curl", "--version"]},
    ),
    _formal_task(
        task_id="jemalloc",
        repository_url="https://github.com/jemalloc/jemalloc",
        commit_sha="0d9d5d553e4ff722a64570a2f7c97399e5d37963",
        source_snapshot_sha256="33b5aa0cd4e3c38beb6b5392aec181a7642b3cb38e58228771b100da0a8a9f74",
        build_system="autotools",
        fault_file="src/jemalloc.c",
        configure_commands=["./autogen.sh --disable-shared --enable-static"],
        configure_repair_commands=["./autogen.sh --disable-shared --enable-static"],
        build_commands=["make -j4"],
        artifact_stage_commands=[
            "mkdir -p /artifacts/lib /artifacts/include && cp lib/libjemalloc.a /artifacts/lib/ && cp -r include/jemalloc /artifacts/include/"
        ],
        required_artifacts=["include/jemalloc/jemalloc.h", "lib/libjemalloc.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <jemalloc/jemalloc.h>\nint main(void){void*p=mallocx(32,0);if(!p)return 1;dallocx(p,0);return 0;}\n",
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libjemalloc.a",
                "-pthread",
                "-ldl",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
    ),
    _formal_task(
        task_id="wolfssl",
        repository_url="https://github.com/wolfSSL/wolfssl",
        commit_sha="7499fc5b6c99eb39055a59f538bb3709971341c9",
        source_snapshot_sha256="00e76dbaf04690265d73bdda58faf78650ce930db6e489a704220c0636cbf755",
        build_system="autotools",
        fault_file="src/ssl.c",
        configure_commands=[
            "./autogen.sh",
            "./configure --disable-shared --enable-static --disable-examples --disable-crypttests",
        ],
        configure_repair_commands=[
            "./autogen.sh",
            "./configure --disable-shared --enable-static --disable-examples --disable-crypttests",
        ],
        build_commands=["make -j4"],
        artifact_stage_commands=[
            "mkdir -p /artifacts/lib /artifacts/include && cp src/.libs/libwolfssl.a /artifacts/lib/ && tar --exclude=wolfssl/wolfcrypt/fips.h -cf - wolfssl | tar -xf - -C /artifacts/include"
        ],
        required_artifacts=["include/wolfssl/ssl.h", "lib/libwolfssl.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <wolfssl/options.h>\n#include <wolfssl/ssl.h>\nint main(void){return wolfSSL_lib_version_hex()>0?0:1;}\n",
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libwolfssl.a",
                "-pthread",
                "-lm",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
    ),
)

CASE_SPECS = (
    {
        "task_id": "libgit2",
        "fault_type": "invalid_build_state",
        "expected_action": "configure",
    },
    {
        "task_id": "simdjson",
        "fault_type": "wrong_build_target",
        "expected_action": "build",
    },
    {
        "task_id": "benchmark",
        "fault_type": "missing_compile_input",
        "expected_action": "dependency",
    },
    {
        "task_id": "pcre2",
        "fault_type": "invalid_build_state",
        "expected_action": "configure",
    },
    {
        "task_id": "haproxy",
        "fault_type": "wrong_build_target",
        "expected_action": "build",
    },
    {
        "task_id": "cc65",
        "fault_type": "missing_compile_input",
        "expected_action": "dependency",
    },
    {
        "task_id": "quickjs",
        "fault_type": "invalid_build_state",
        "expected_action": "configure",
    },
    {
        "task_id": "redis",
        "fault_type": "wrong_build_target",
        "expected_action": "build",
    },
    {
        "task_id": "libarchive",
        "fault_type": "missing_compile_input",
        "expected_action": "dependency",
    },
    {
        "task_id": "curl",
        "fault_type": "invalid_build_state",
        "expected_action": "configure",
    },
    {
        "task_id": "jemalloc",
        "fault_type": "wrong_build_target",
        "expected_action": "build",
    },
    {
        "task_id": "wolfssl",
        "fault_type": "missing_compile_input",
        "expected_action": "dependency",
    },
)


def _build_schedule() -> tuple[tuple[str, str], ...]:
    latin = (
        ("always_agent", "rule_gate_agent", "jev_gate_agent"),
        ("rule_gate_agent", "jev_gate_agent", "always_agent"),
        ("jev_gate_agent", "always_agent", "rule_gate_agent"),
    )
    rows: list[tuple[str, str]] = []
    for repetition in range(1, REPETITIONS + 1):
        for index, case in enumerate(CASE_SPECS):
            for arm in latin[(index + repetition - 1) % len(latin)]:
                rows.append((case["task_id"], arm))
    return tuple(rows)


SCHEDULE = _build_schedule()
AGENT_BUDGET = {
    "max_model_requests": 24,
    "max_recorded_tokens": 300_000,
    "max_agent_steps": 64,
    "max_tool_calls": 48,
    "max_commands": 32,
    "node_timeout_seconds": 1_800,
    "command_timeout_seconds": 900,
    "evaluator_timeout_seconds": 1_800,
    "replay_timeout_seconds": 1_800,
    "cleanup_timeout_seconds": 120,
}
TOTAL_AGENT_REQUEST_CEILING = 1_728
TOTAL_AGENT_TOKEN_CEILING = 21_600_000
TOTAL_JEV_REQUEST_CEILING = 24
TOTAL_JEV_INPUT_TOKEN_CEILING = 480_000
TOTAL_JEV_COST_CEILING_USD = 0.02016

CALIBRATION = CalibrationContract(
    model="jev-1.13.0",
    coefficient=0.08805149266059632,
    intercept=0.618335523488825,
    threshold=0.6747568477098429,
)
VERIFIER_CAPABILITIES = VerifierCapabilities(True, True, True, True)


class CanaryError(RuntimeError):
    """正式比较身份、预算、evidence 或运行合同无效。"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CanaryError(f"JSON 根必须为对象: {path}")
    return value


def _write_once(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        path.chmod(0o600)
    except FileExistsError as exc:
        raise CanaryError(f"create-once 路径已存在: {path}") from exc


def _write_once_json(path: Path, value: Any) -> None:
    _write_once(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
    )


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)
    path.chmod(0o600)


def _git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise CanaryError(result.stderr.strip() or f"git {' '.join(arguments)} 失败")
    return result.stdout.strip()


def _git_blob_sha256(revision: str, path: Path) -> str:
    relative = path.relative_to(REPO_ROOT).as_posix()
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative}"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise CanaryError(f"无法读取 {revision}:{relative}")
    return hashlib.sha256(result.stdout).hexdigest()


def _task(task_id: str) -> dict[str, Any]:
    matches = [task for task in TASKS if task["task_id"] == task_id]
    if len(matches) != 1:
        raise CanaryError(f"未知 task: {task_id}")
    return dict(matches[0])


def _repetition_for_sequence(sequence: int) -> int:
    block = len(CASE_SPECS) * len(ARMS)
    if sequence < 1 or sequence > len(SCHEDULE):
        raise CanaryError(f"非法 schedule sequence: {sequence}")
    return (sequence - 1) // block + 1


def _case(task_id: str) -> dict[str, str]:
    matches = [case for case in CASE_SPECS if case["task_id"] == task_id]
    if len(matches) != 1:
        raise CanaryError(f"未知 case: {task_id}")
    return matches[0]


def _source_contract(task: dict[str, Any]) -> dict[str, Any]:
    return {
        key: task[key]
        for key in (
            "task_id",
            "project_family",
            "repository_url",
            "commit_sha",
            "source_snapshot_sha256",
            "selected_build_system",
            "fault_file",
            "configure_commands",
            "configure_repair_commands",
            "build_commands",
            "artifact_stage_commands",
            "target",
            "oracle",
        )
    }


def build_manifest(implementation_revision: str) -> dict[str, Any]:
    revision = _git("rev-parse", "--verify", f"{implementation_revision}^{{commit}}")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise CanaryError("implementation revision 必须为完整 commit")
    components = {
        SCRIPT_PATH.relative_to(REPO_ROOT).as_posix(): _git_blob_sha256(
            revision, SCRIPT_PATH
        ),
        "backend/packages/harness/deerflow/compile/jev_controller.py": _git_blob_sha256(
            revision,
            REPO_ROOT / "backend/packages/harness/deerflow/compile/jev_controller.py",
        ),
        "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py": _git_blob_sha256(
            revision,
            REPO_ROOT
            / "backend/packages/harness/deerflow/compile/agent_workflow_runtime.py",
        ),
        "backend/packages/harness/deerflow/compile/external_evaluator_v2.py": _git_blob_sha256(
            revision,
            REPO_ROOT
            / "backend/packages/harness/deerflow/compile/external_evaluator_v2.py",
        ),
    }
    return {
        "$schema": "../schemas/forge-jev-formal-comparison-v5.schema.json",
        "schema_version": SCHEMA_VERSION,
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "branch": BRANCH,
        "implementation_revision": revision,
        "components": components,
        "parents": {
            path.relative_to(REPO_ROOT).as_posix(): file_sha256(path)
            for path in PARENT_PATHS
        },
        "cases": [
            {
                **_case(case["task_id"]),
                "source": _source_contract(_task(case["task_id"])),
            }
            for case in CASE_SPECS
        ],
        "arms": list(ARMS),
        "schedule": [
            {
                "sequence": index,
                "repetition": _repetition_for_sequence(index),
                "task_id": task_id,
                "arm": arm,
            }
            for index, (task_id, arm) in enumerate(SCHEDULE, start=1)
        ],
        "analysis": {
            "evaluation_cutoff": EVALUATION_CUTOFF,
            "project_family_clustered_bootstrap": True,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "noninferiority_margin": NONINFERIORITY_MARGIN,
            "minimum_provider_cost_reduction": MINIMUM_COST_REDUCTION,
            "primary_comparison": ["jev_gate_agent", "always_agent"],
            "secondary_baseline": "rule_gate_agent",
            "rmst_tau_seconds": AGENT_BUDGET["node_timeout_seconds"],
        },
        "routing": {
            "rule_gate_action": "build",
            "jev_model": CALIBRATION.model,
            "jev_calibration": asdict(CALIBRATION),
            "candidate_actions": ["dependency", "configure", "build", "escalate_agent"],
            "direct_action_terminal_success_allowed": False,
            "agent_escalation_on_direct_action_failure": True,
        },
        "agent_provider": {
            "profile": AGENT_PROFILE,
            "endpoint": AGENT_ENDPOINT,
            "credential_env": AGENT_CREDENTIAL_ENV,
            "request_timeout_seconds": AGENT_REQUEST_TIMEOUT_SECONDS,
            "max_retries": AGENT_MAX_RETRIES,
            "cost_estimation": {
                "method": "peak_cache_miss_upper_bound",
                "input_price_usd_per_million_tokens": AGENT_INPUT_PRICE_USD_PER_MILLION_TOKENS,
                "output_price_usd_per_million_tokens": AGENT_OUTPUT_PRICE_USD_PER_MILLION_TOKENS,
                "source": AGENT_PRICING_SOURCE,
                "retrieved_at": "2026-10-11",
            },
        },
        "jev_provider": {
            "model": jev_candidate.MODEL_ID,
            "endpoint": jev_candidate.API_BASE_URL,
            "credential_file": CREDENTIAL_FILE.name,
            "max_retries": 0,
            "request_timeout_seconds": 30,
            "input_price_usd_per_million_tokens": jev_candidate.INPUT_PRICE_USD_PER_MILLION_TOKENS,
        },
        "environment": {
            "compile_image": COMPILE_IMAGE,
            "image_id": EXPECTED_IMAGE_ID,
            "parallel_jobs": 4,
            "network_policy": "compile-network-v1",
            "workspace_root_binding": "repository_root",
        },
        "budget": {
            "per_arm_agent": AGENT_BUDGET,
            "total_agent_request_ceiling": TOTAL_AGENT_REQUEST_CEILING,
            "total_agent_token_ceiling": TOTAL_AGENT_TOKEN_CEILING,
            "total_jev_request_ceiling": TOTAL_JEV_REQUEST_CEILING,
            "total_jev_input_token_ceiling": TOTAL_JEV_INPUT_TOKEN_CEILING,
            "total_jev_cost_ceiling_usd": TOTAL_JEV_COST_CEILING_USD,
        },
        "authorization": {
            "credential_reads": True,
            "provider_calls": True,
            "docker_execution": True,
            "formal_attempts": len(SCHEDULE),
            "formal_evidence_write": True,
            "historical_evidence_write": False,
            "replacement": False,
            "backfill": False,
        },
        "stopping_rules": {
            "stop_batch_on_identity_or_evidence_corruption": True,
            "stop_batch_on_budget_overrun": True,
            "stop_batch_on_cleanup_or_orphan_failure": True,
            "provider_or_model_failure_is_arm_outcome": True,
            "continue_after_behavioral_failure": True,
        },
        "evidence": {
            "root": EVIDENCE_ROOT.relative_to(REPO_ROOT).as_posix(),
            "create_once": True,
            "preserve_failures": True,
            "store_credentials": False,
        },
        "interpretation": {
            "controlled_failure_formal_comparison": True,
            "natural_failure_generalization": False,
            "strict_success_noninferiority": True,
            "cost_savings_claim": True,
            "dynamic_budget_claim": False,
        },
    }


def build_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-jev-formal-comparison-v5.schema.json",
        "title": "Forge Jev formal comparison v5",
        "const": manifest,
    }


def render_preregistration(manifest: dict[str, Any]) -> str:
    schedule = "\n".join(
        f"{row['sequence']}. repetition `{row['repetition']}` / `{row['task_id']}` / `{row['arm']}`"
        for row in manifest["schedule"]
    )
    cases = "\n".join(
        f"- `{case['task_id']}` / `{case['source']['selected_build_system']}` / "
        f"`{case['fault_type']}` / 预期 `{case['expected_action']}`"
        for case in manifest["cases"]
    )
    return f"""# Jev 未见项目族正式三臂比较 v5

- Tracking Issue：[#408]({ISSUE_URL})
- Identity：`{IDENTITY}`
- Implementation revision：`{manifest["implementation_revision"]}`
- Manifest canonical SHA-256：`{canonical_sha256(manifest)}`

## 研究问题

在 12 个未参与 Jev 资格、校准或 canary 的项目族上，`JevGate+Agent` 能否相对
`AlwaysAgent` 保持严格成功率非劣并降低 Provider 成本？`RuleGate+Agent` 作为冻结的简单规则基线。

样本覆盖 CMake、Make、Autotools 各四个项目，exact commit 均晚于
`{EVALUATION_CUTOFF}`。每个项目、每个 arm 独立运行两次，共 72 arms。
故障均为受控故障，结论不得外推到自然失败分布。

v4 的 12 项零 Provider 资格中 10 项严格通过。Redis 因构建 ID 使用容器主机名和当前时间而在
clean replay 发生 bitwise 不一致；WolfSSL 因递归暂存包含唯一的 0 字节占位头文件而被 external
evaluator 拒绝。v5 只为 Redis 固定 exact-commit 的 `SOURCE_DATE_EPOCH`，并在 WolfSSL 暂存时排除
该空占位文件。隔离诊断已验证两次 Redis clean build 完全一致，WolfSSL 剩余非空文件与功能 oracle
通过。其余 10 个项目、三臂、顺序、模型、阈值、预算、统计和停止规则均保持不变。v1-v4 不续跑、
不 backfill，正式 arm 尚未创建。

## 样本

{cases}

## 固定顺序

{schedule}

## 三臂

- `always_agent`：故障状态直接升级完整 Agent。
- `rule_gate_agent`：固定选择 `build`；动作失败时升级完整 Agent，动作成功时由确定性 continuation 和同一 evaluator 收口。
- `jev_gate_agent`：Jev 以正序/逆序 Choice 判断动作，经冻结 Platt 门禁后直接执行或升级 Agent；动作失败时升级完整 Agent。

直接动作只执行代码绑定命令，不能生成 Shell，也不能宣告成功。所有候选必须经过 CandidateVerifier、functional oracle、provenance 和 clean replay。

## 固定预算

- 每 arm Agent：最多 {AGENT_BUDGET["max_model_requests"]} 请求、{AGENT_BUDGET["max_recorded_tokens"]} tokens、{AGENT_BUDGET["node_timeout_seconds"]} 秒；
- 全阶段 Agent：最多 {TOTAL_AGENT_REQUEST_CEILING} 请求、{TOTAL_AGENT_TOKEN_CEILING} tokens；
- Jev：最多 {TOTAL_JEV_REQUEST_CEILING} 请求、{TOTAL_JEV_INPUT_TOKEN_CEILING} input tokens、`${TOTAL_JEV_COST_CEILING_USD}`；
- Provider retry 均为 0；不存在 replacement 或 backfill。

## 主要判据与统计

- 项目族聚类 bootstrap：seed `{BOOTSTRAP_SEED}`，重复 `{BOOTSTRAP_SAMPLES}` 次；
- Jev 相对 AlwaysAgent 的 strict success 差值单侧 95% 下界不低于 `{NONINFERIORITY_MARGIN:.0%}`；
- Jev 相对 AlwaysAgent 的总 Provider 成本至少下降 `{MINIMUM_COST_REDUCTION:.0%}`；
- 两项必须同时成立，才支持正向主结论；同时报告分构建系统结果、RMST、请求、tokens、升级率和错误直接动作率。

## 停止规则

identity/evidence 损坏、预算越界、cleanup/orphan 失败立即停止整个 batch。Provider、模型行为、
无候选、超时和严格验证失败均保留为 arm outcome；不 replacement、不 backfill、不依据正式结果改阈值。

## 解释边界

本实验只支持对受控构建失败、冻结模型和当前 12 个项目族总体的推断；不支持自然失败泛化、
通用模型排名或动态预算优越性。直接动作不能绕过 CandidateVerifier、functional oracle、provenance 或 clean replay。
"""


def bind_identity(implementation_revision: str) -> dict[str, Any]:
    manifest = build_manifest(implementation_revision)
    _write_once_json(MANIFEST_PATH, manifest)
    _write_once_json(SCHEMA_PATH, build_schema(manifest))
    _write_once(PREREGISTRATION_PATH, render_preregistration(manifest))
    return manifest


def validate_manifest() -> dict[str, Any]:
    manifest = _load_json(MANIFEST_PATH)
    expected = build_manifest(manifest.get("implementation_revision", ""))
    if manifest != expected:
        raise CanaryError("manifest 与冻结生成结果不一致")
    schema = _load_json(SCHEMA_PATH)
    if schema != build_schema(expected):
        raise CanaryError("const Schema 漂移")
    jsonschema.validate(manifest, schema)
    if PREREGISTRATION_PATH.read_text(encoding="utf-8") != render_preregistration(
        expected
    ):
        raise CanaryError("预注册文本漂移")
    return manifest


def validate_parents() -> None:
    manifest = validate_manifest()
    for relative, digest in manifest["parents"].items():
        if file_sha256(REPO_ROOT / relative) != digest:
            raise CanaryError(f"父报告漂移: {relative}")
    canary_manifest = _load_json(CANARY_V7_MANIFEST_PATH)
    canary_qualification = _load_json(CANARY_V7_QUALIFICATION_PATH)
    canary_report = _load_json(CANARY_V7_REPORT_PATH)
    v1_failure = _load_json(V1_QUALIFICATION_FAILURE_PATH)
    v2_failure = _load_json(V2_QUALIFICATION_FAILURE_PATH)
    v3_failure = _load_json(V3_QUALIFICATION_FAILURE_PATH)
    v4_qualification = _load_json(V4_QUALIFICATION_PATH)
    v4_failure = _load_json(V4_QUALIFICATION_FAILURE_PATH)
    if (
        canary_manifest.get("identity") != "cpp-jev-end-to-end-canary-v7"
        or canary_qualification.get("decision") != "proceed_to_formal_canary"
        or canary_report.get("decision")
        != "proceed_to_formal_end_to_end_comparison_design"
        or v1_failure.get("decision") != "supersede_with_fresh_v2_identity"
        or v1_failure.get("observed_counts", {}).get("provider_calls") != 0
        or v1_failure.get("observed_counts", {}).get("formal_attempts") != 0
        or v2_failure.get("decision") != "supersede_with_fresh_v3_identity"
        or v2_failure.get("observed_counts", {}).get("provider_calls") != 0
        or v2_failure.get("observed_counts", {}).get("formal_attempts") != 0
        or v3_failure.get("decision")
        != "supersede_with_fresh_v4_identity_and_replace_incompatible_case"
        or v3_failure.get("observed_counts", {}).get("provider_calls") != 0
        or v3_failure.get("observed_counts", {}).get("formal_attempts") != 0
        or v4_qualification.get("identity") != "cpp-jev-formal-comparison-v4"
        or v4_qualification.get("decision") != "stop_before_formal_comparison"
        or sum(
            row.get("strict_success") is True
            for row in v4_qualification.get("rows", [])
        )
        != 10
        or v4_failure.get("decision")
        != "supersede_with_fresh_v5_identity_and_repair_two_project_contracts"
        or v4_failure.get("observed_counts", {}).get("provider_calls") != 0
        or v4_failure.get("observed_counts", {}).get("formal_attempts") != 0
    ):
        raise CanaryError("formal comparison 父证据无效")


def _configure_compile_workspace(manifest: dict[str, Any]) -> dict[str, str]:
    if manifest["environment"].get("workspace_root_binding") != "repository_root":
        raise CanaryError("Compile Session workspace binding 漂移")
    root = REPO_ROOT.resolve()
    os.environ["DEER_FLOW_WORKSPACE_ROOT"] = str(root)
    os.environ["DEER_FLOW_HOST_WORKSPACE_ROOT"] = str(root)
    services = get_compile_services()
    process_root = get_compile_sessions_root(services.manager.paths).resolve()
    host_root = Path(get_host_compile_sessions_root(services.manager.paths)).resolve()
    expected = root / ".compile-sessions"
    if process_root != expected or host_root != expected:
        raise CanaryError("Compile Session workspace 未绑定到 repository root")
    return {
        "binding": "repository_root",
        "process_root": ".compile-sessions",
        "host_root": ".compile-sessions",
    }


def _image_id() -> str:
    result = subprocess.run(
        ["docker", "image", "inspect", COMPILE_IMAGE, "--format", "{{.Id}}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise CanaryError("无法读取编译镜像")
    return result.stdout.strip()


def preflight(
    *, require_clean: bool = True, require_absent_evidence: bool = True
) -> dict[str, Any]:
    manifest = validate_manifest()
    validate_parents()
    _qualification_report()
    workspace = _configure_compile_workspace(manifest)
    if _git("branch", "--show-current") != BRANCH:
        raise CanaryError("当前分支与实验身份不一致")
    if require_clean and _git("status", "--porcelain"):
        raise CanaryError("正式运行要求干净工作树")
    head = _git("rev-parse", "HEAD")
    if (
        subprocess.run(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                manifest["implementation_revision"],
                head,
            ],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
        != 0
    ):
        raise CanaryError("HEAD 不是 implementation revision 后代")
    if f"origin/{BRANCH}" not in {
        row.strip() for row in _git("branch", "-r", "--contains", head).splitlines()
    }:
        raise CanaryError("正式运行 revision 尚未推送")
    for relative, digest in manifest["components"].items():
        if file_sha256(REPO_ROOT / relative) != digest:
            raise CanaryError(f"实现组件漂移: {relative}")
    if _image_id() != manifest["environment"]["image_id"]:
        raise CanaryError("编译镜像漂移")
    if not CREDENTIAL_FILE.is_file() or CREDENTIAL_FILE.stat().st_mode & 0o777 != 0o600:
        raise CanaryError("Jev credential 文件必须存在且权限为 600")
    if not os.environ.get(AGENT_CREDENTIAL_ENV):
        raise CanaryError("完整 Agent credential 环境变量未注入")
    if require_absent_evidence and EVIDENCE_ROOT.exists():
        raise CanaryError("正式 evidence root 已存在")
    if require_absent_evidence and (
        JSON_REPORT_PATH.exists() or MARKDOWN_REPORT_PATH.exists()
    ):
        raise CanaryError("正式报告路径必须不存在")
    agent_runner.require_zero_managed_resources()
    jev_v6.validate_egress()
    return {
        "ready": True,
        "identity": IDENTITY,
        "git_commit": head,
        "manifest_sha256": canonical_sha256(manifest),
        "image_id": _image_id(),
        "workspace": workspace,
        "credential_reads": 0,
        "provider_calls": 0,
        "formal_attempts": 0,
        "evidence_exists": EVIDENCE_ROOT.exists(),
        "zero_managed_resources": True,
    }


def _commands(task: dict[str, Any], fault_type: str, action_family: str) -> list[str]:
    if action_family == "dependency":
        return [f"git checkout HEAD -- {shlex.quote(task['fault_file'])}"]
    if action_family == "configure":
        return list(task["configure_repair_commands"])
    if action_family == "build":
        return list(task["build_commands"])
    raise CanaryError(f"不可直接执行动作: {action_family}")


def _candidate_actions(state: dict[str, Any]) -> tuple[CandidateAction, ...]:
    return tuple(
        CandidateAction(
            action_id=row["action_id"],
            action_family=row["action_family"],
            bound_commands=tuple(row["bound_commands"]),
            direct_execution=row["direct_execution"],
            preconditions_satisfied=row["preconditions_checked_by_runner"],
        )
        for row in state["candidate_actions"]
    )


def _decision_state(state: dict[str, Any], fingerprint: str) -> DecisionState:
    return DecisionState(
        state_id=state["state_id"],
        build_system=state["build_system"],
        phase_facts=state["phase_facts"],
        remaining_actions=8,
        remaining_wall_clock_seconds=900,
        expected_request_fingerprint=fingerprint,
    )


def rule_route(state: dict[str, Any]) -> str:
    del state
    return "build"


def _read_jev_credential() -> str:
    if CREDENTIAL_FILE.stat().st_mode & 0o777 != 0o600:
        raise CanaryError("Jev credential 权限漂移")
    value = CREDENTIAL_FILE.read_text(encoding="utf-8").strip()
    if not value or "\n" in value or "\r" in value:
        raise CanaryError("Jev credential 必须只有一行")
    return value


def request_jev(state: dict[str, Any]) -> tuple[TypedDecision, dict[str, Any]]:
    prompt = jev_v6._prompt_contract(2)
    provider_state = jev_candidate.provider_state(state["model_input"])
    questions = jev_v6._provider_questions(prompt)
    fingerprint = jev_candidate.request_fingerprint(provider_state, questions)
    logging.getLogger("typesafe_sdk").disabled = True
    key = _read_jev_credential()
    started = time.perf_counter()
    with jev_v6._provider_http_client() as http_client:
        with TypeSafeClient(
            api_key=key,
            model=jev_candidate.MODEL_ID,
            retry=RetryPolicy(max_retries=0, timeout=30.0),
            base_url=jev_candidate.API_BASE_URL,
            http_client=http_client,
        ) as client:
            response = client.system_one(state=provider_state, questions=questions)
    key = ""
    normalized = jev_v6.normalize_response(
        response, latency_ms=(time.perf_counter() - started) * 1000
    )
    primary = normalized["answers"]["next_action_primary"]
    reverse = normalized["answers"]["next_action_order_sensitivity"]
    decision = TypedDecision(
        state_id=state["state_id"],
        model=normalized["model"],
        request_fingerprint=fingerprint,
        primary_choice=primary["choice"],
        reverse_choice=reverse["choice"],
        probabilities=primary["probabilities"],
        reverse_probabilities=reverse["probabilities"],
    )
    return decision, {"request_fingerprint": fingerprint, "response": normalized}


def choose_jev_route(
    state: dict[str, Any], decision: TypedDecision
) -> tuple[str, dict[str, Any]]:
    route = route_next_action(
        state=_decision_state(state, decision.request_fingerprint),
        candidates=_candidate_actions(state),
        decision=decision,
        calibration=CALIBRATION,
        verifier_capabilities=VERIFIER_CAPABILITIES,
    )
    receipt = dispatch_route(
        route=route, candidates=_candidate_actions(state), executor=lambda _: None
    )
    return route.selected_action_family, {
        "disposition": route.disposition,
        "selected_action_id": route.selected_action_id,
        "selected_action_family": route.selected_action_family,
        "calibrated_safe_probability": route.calibrated_safe_probability,
        "reasons": list(route.reasons),
        "dispatch_disposition": receipt.disposition,
    }


def _zero_provider_qualification_case(
    manifest: dict[str, Any],
    case: dict[str, str],
    *,
    sequence: int,
    ledger_root: Path,
) -> dict[str, Any]:
    task = _task(case["task_id"])
    digest = canonical_sha256(manifest)
    thread_id = f"jev-formal-qualification-{sequence:02d}-{digest[:10]}"
    services = get_compile_services()
    ledger = ExperimentLedger.create(
        ledger_root / f"{sequence:02d}-{task['task_id']}.jsonl",
        experiment_id=new_evidence_id("qualification_experiment"),
        physical_attempt_id=new_evidence_id("qualification_attempt"),
        context={
            "identity": IDENTITY,
            "manifest_sha256": digest,
            "task_id": task["task_id"],
            "qualification": True,
        },
    )
    session = None
    active = False
    cleaned = False
    try:
        activate_experiment(
            thread_id=thread_id,
            experiment_id=ledger.experiment_id,
            physical_attempt_id=ledger.physical_attempt_id,
            ledger=ledger,
            policy=_experiment_policy(
                manifest, task, "zero_provider_qualification", sequence
            ),
        )
        active = True
        session = prepare_compile_session_impl(
            thread_id=thread_id,
            repo_url=task["repository_url"],
            run_id=f"jev-formal-qualification-{uuid.uuid4().hex}",
            task_description=(
                f"Jev formal comparison zero-provider qualification: {task['task_id']}"
            ),
        )
        clone, _message = clone_repository_impl(
            session=session,
            repo_url=task["repository_url"],
            commit_sha=task["commit_sha"],
            depth=1,
            max_retries=1,
        )
        if clone.exit_code != 0 or session.commit_sha != task["commit_sha"]:
            raise CanaryError(f"{task['task_id']} qualification 无法检出冻结 commit")
        primary, detected_systems, selected = _select_experiment_build_system(
            session, task
        )
        configured, baseline_records, _configure_message = _run_bound_commands(
            session,
            list(task["configure_commands"]),
            "configure",
            require_success=True,
        )
        if not configured:
            raise CanaryError(f"{task['task_id']} qualification configure 失败")
        state, failure_record = _inject_fault(session, task, case["fault_type"], ledger)
        action_succeeded, action_records, _action_message = _run_bound_commands(
            session,
            _commands(task, case["fault_type"], case["expected_action"]),
            case["expected_action"],
            require_success=True,
        )
        build_records = action_records if case["expected_action"] == "build" else []
        if case["expected_action"] != "build":
            action_succeeded, build_records, _build_message = _run_bound_commands(
                session,
                list(task["build_commands"]),
                "build",
                require_success=True,
            )
        stage_succeeded, stage_records, _stage_message = _run_bound_commands(
            session,
            list(task["artifact_stage_commands"]),
            "artifact_stage",
            require_success=True,
        )
        route_observation = {
            "controller": "zero_provider_qualification",
            "selected_action_family": case["expected_action"],
            "failure_command_id": failure_record.command_id,
            "state_id": state["state_id"],
            "build_system_detection": {
                "primary": primary,
                "detected": detected_systems,
                "selected": selected,
            },
        }
        attempt_id = f"formal-qualification-{sequence:02d}-direct"
        node_input = _node_input(
            manifest, task, session, attempt_id, state, route_observation
        )
        recipe_records = [*baseline_records, *action_records]
        if case["expected_action"] != "build":
            recipe_records.extend(build_records)
        recipe_records.extend(stage_records)
        node_result, candidate_path = _direct_candidate(
            node_input=node_input,
            session=session,
            manager=services.manager,
            sequence=sequence,
            arm="qualification",
            recipe_records=recipe_records,
            supporting_record=build_records[-1],
        )
        evaluation = _evaluate(
            node_input=node_input,
            node_result=node_result,
            session=session,
            candidate_path=candidate_path,
            evaluation_id=f"formal-qualification-{sequence:02d}",
        )
        finalized, cleanup = _safe_cleanup(session)
        cleaned = True
        return {
            "task_id": task["task_id"],
            "build_system": task["selected_build_system"],
            "build_system_detection": route_observation["build_system_detection"],
            "fault_type": case["fault_type"],
            "expected_action": case["expected_action"],
            "state_id": state["state_id"],
            "fault_exit_code": failure_record.exit_code,
            "action_succeeded": action_succeeded,
            "artifact_stage_succeeded": stage_succeeded,
            "candidate_submitted": node_result.candidate_submitted,
            "s0_s5": [asdict(layer) for layer in evaluation.layers],
            "strict_success": evaluation.strict_reproducible_build_success,
            "session_status": finalized.status,
            "cleanup_succeeded": cleanup.succeeded,
        }
    finally:
        try:
            if session is not None and not cleaned:
                _safe_cleanup(session)
        finally:
            if active:
                deactivate_experiment(thread_id)


def zero_provider_qualification() -> dict[str, Any]:
    manifest = validate_manifest()
    validate_parents()
    workspace = _configure_compile_workspace(manifest)
    if _image_id() != manifest["environment"]["image_id"]:
        raise CanaryError("编译镜像漂移")
    agent_runner.require_zero_managed_resources()
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix="forge-jev-formal-qualification-"
    ) as temporary:
        ledger_root = Path(temporary)
        for sequence, case in enumerate(CASE_SPECS, start=1):
            rows.append(
                _zero_provider_qualification_case(
                    manifest, case, sequence=sequence, ledger_root=ledger_root
                )
            )
    agent_runner.require_zero_managed_resources()
    gates = {
        "all_build_systems": {row["build_system"] for row in rows}
        == {"cmake", "make", "autotools"},
        "authoritative_build_system_selected": all(
            row["build_system_detection"]["selected"] == row["build_system"]
            for row in rows
        ),
        "all_faults_triggered": all(
            row["fault_exit_code"] not in (None, 0) for row in rows
        ),
        "all_actions_succeeded": all(row["action_succeeded"] for row in rows),
        "all_artifacts_staged": all(row["artifact_stage_succeeded"] for row in rows),
        "all_candidates_submitted": all(row["candidate_submitted"] for row in rows),
        "all_s0_s5_passed": all(
            row["strict_success"]
            and len(row["s0_s5"]) == 6
            and all(layer["status"] == "passed" for layer in row["s0_s5"])
            for row in rows
        ),
        "all_compile_sessions_cleaned": all(
            row["cleanup_succeeded"] and row["session_status"] == "completed"
            for row in rows
        ),
        "zero_managed_resources": True,
        "zero_provider": True,
        "zero_credential_read": True,
    }
    report = {
        "schema_version": "forge-jev-formal-comparison-qualification-5.0.0",
        "identity": IDENTITY,
        "manifest_sha256": canonical_sha256(manifest),
        "created_at": _now(),
        "workspace": workspace,
        "rows": rows,
        "gates": gates,
        "passed": all(gates.values()),
        "decision": "proceed_to_formal_comparison"
        if all(gates.values())
        else "stop_before_formal_comparison",
        "provider_calls": 0,
        "credential_reads": 0,
        "formal_attempts": 0,
    }
    if QUALIFICATION_JSON_PATH.exists() or QUALIFICATION_MARKDOWN_PATH.exists():
        raise CanaryError("qualification 报告已存在")
    _write_once_json(QUALIFICATION_JSON_PATH, report)
    _write_once(
        QUALIFICATION_MARKDOWN_PATH,
        "# Jev 未见项目族正式三臂比较 v5 零 Provider 资格报告\n\n"
        f"- 决定：`{report['decision']}`\n"
        f"- 真实 Compile Session 严格成功：`{sum(row['strict_success'] for row in rows)}/{len(CASE_SPECS)}`\n"
        "- Provider / credential / formal attempt：`0 / 0 / 0`\n\n"
        "该门禁覆盖故障注入、authoritative build-system selection、代码绑定动作、"
        "Candidate 提交、S0-S5 external evaluator、clean replay 和 cleanup；不证明三臂效果。\n",
    )
    return report


def _qualification_report() -> dict[str, Any]:
    if (
        not QUALIFICATION_JSON_PATH.is_file()
        or not QUALIFICATION_MARKDOWN_PATH.is_file()
    ):
        raise CanaryError("缺少已提交的零 Provider 资格报告")
    report = _load_json(QUALIFICATION_JSON_PATH)
    manifest = validate_manifest()
    if report.get("identity") != IDENTITY or report.get(
        "manifest_sha256"
    ) != canonical_sha256(manifest):
        raise CanaryError("qualification 报告 identity 漂移")
    if (
        report.get("passed") is not True
        or report.get("decision") != "proceed_to_formal_comparison"
    ):
        raise CanaryError("零 Provider 资格门禁未通过")
    return report


def _experiment_policy(
    manifest: dict[str, Any], task: dict[str, Any], arm: str, sequence: int
) -> ExperimentPolicy:
    return ExperimentPolicy(
        benchmark_id=IDENTITY,
        manifest_sha256=canonical_sha256(manifest),
        case_id=f"{sequence:02d}-{task['task_id']}",
        condition=arm,
        repetition=_repetition_for_sequence(sequence),
        expected_repo_url=task["repository_url"],
        expected_commit_sha=task["commit_sha"],
        expected_build_system=task["selected_build_system"],
        compile_image=manifest["environment"]["compile_image"],
        image_id=manifest["environment"]["image_id"],
        model_name=AGENT_PROFILE,
        endpoint=AGENT_ENDPOINT,
        credential_env=AGENT_CREDENTIAL_ENV,
        request_timeout_seconds=AGENT_REQUEST_TIMEOUT_SECONDS,
        model_max_retries=AGENT_MAX_RETRIES,
        compiler_max_turns=AGENT_BUDGET["max_model_requests"],
        subagent_timeout_seconds=AGENT_BUDGET["node_timeout_seconds"],
        memory_enabled=False,
        skills_enabled=False,
        required_system_packages=(),
        cmake_arguments=(),
        configure_arguments=(),
        environment=(),
        minimum_replay_delay_seconds=0,
        compiler_model_turn_limit=AGENT_BUDGET["max_model_requests"],
        compiler_graph_recursion_limit=AGENT_BUDGET["max_agent_steps"],
        compiler_wall_clock_seconds=AGENT_BUDGET["node_timeout_seconds"],
        compiler_post_build_reserve_seconds=AGENT_BUDGET["cleanup_timeout_seconds"],
    )


def _oracle_ref(task: dict[str, Any]) -> str:
    return f"{task['task_id']}-functional-oracle-v1"


def _compiled_target(task: dict[str, Any]) -> tuple[str, str]:
    compiled_types = {"executable", "shared_library", "static_library", "object"}
    matches = [
        (path, artifact_type)
        for path, artifact_type in zip(
            task["target"]["required_artifacts"],
            task["target"]["artifact_types"],
            strict=True,
        )
        if artifact_type in compiled_types
    ]
    if len(matches) != 1:
        raise CanaryError(f"{task['task_id']} 必须只有一个编译目标产物")
    return matches[0]


def _node_input(
    manifest: dict[str, Any],
    task: dict[str, Any],
    session: Any,
    attempt_id: str,
    state: dict[str, Any],
    route_observation: dict[str, Any],
) -> AgentBuildNodeInput:
    _target_path, target_type = _compiled_target(task)
    return AgentBuildNodeInput(
        task_id=task["task_id"],
        attempt_id=attempt_id,
        session_id=session.session_id,
        repository_url=task["repository_url"],
        commit_sha=task["commit_sha"],
        source_snapshot_sha256=task["source_snapshot_sha256"],
        build_system_candidates=(task["selected_build_system"],),
        target_contract=AgentWorkflowTargetContract(
            target_id=f"{task['task_id']}-target",
            artifact_types=(target_type,),
            artifact_path_patterns=tuple(task["target"]["required_artifacts"]),
            functional_oracle_ref=_oracle_ref(task),
        ),
        operation_policy_ref="compile-operation-policy-v1",
        environment=AgentWorkflowEnvironmentIdentity(
            image_id=manifest["environment"]["image_id"],
            parallel_jobs=manifest["environment"]["parallel_jobs"],
            network_policy=manifest["environment"]["network_policy"],
        ),
        budget=AgentWorkflowBudget(**AGENT_BUDGET),
        experiment_identity=AgentWorkflowExperimentIdentity(
            manifest_sha256=canonical_sha256(manifest),
            protocol_sha256=file_sha256(PREREGISTRATION_PATH),
            runner_sha256=manifest["components"][
                SCRIPT_PATH.relative_to(REPO_ROOT).as_posix()
            ],
        ),
        initial_observation={
            "fault_type": _case(task["task_id"])["fault_type"],
            "semantic_failure_log": state["semantic_failure_log"],
            "candidate_action_families": tuple(
                row["action_family"] for row in state["candidate_actions"]
            ),
            "required_candidate_artifacts": tuple(task["target"]["required_artifacts"]),
            "functional_oracle": task["oracle"],
            "selected_build_system": task["selected_build_system"],
            "route_observation": route_observation,
        },
    )


def _oracle_spec(task: dict[str, Any]) -> FunctionalOracleSpec:
    oracle = task["oracle"]
    oracle_ref = _oracle_ref(task)
    if oracle["kind"] == "command":
        return FunctionalOracleSpec(
            oracle_ref=oracle_ref,
            argv=tuple(oracle["argv"]),
            workdir="/workspace/repo",
            timeout_seconds=120,
            requires_explicit_relative_executable=True,
        )
    if oracle["kind"] == "compile_and_run":
        suffix = ".c" if oracle["language"] == "c11" else ".cc"
        source_path = f"/workspace/forge-jev-formal-{task['task_id']}{suffix}"
        executable_path = f"/workspace/forge-jev-formal-{task['task_id']}"
        encoded = base64.b64encode(oracle["source"].encode("utf-8")).decode("ascii")
        compile_argv = [
            source_path
            if item == "{source}"
            else executable_path
            if item == "{executable}"
            else item
            for item in oracle["compile_argv"]
        ]
        run_argv = [
            executable_path if item == "{executable}" else item
            for item in oracle["run_argv"]
        ]
        command = (
            f"printf %s {shlex.quote(encoded)} | base64 -d > {shlex.quote(source_path)}"
            f" && {shlex.join(compile_argv)} && {shlex.join(run_argv)}"
        )
        return FunctionalOracleSpec(
            oracle_ref=oracle_ref,
            argv=("sh", "-c", command),
            workdir="/workspace",
            timeout_seconds=120,
        )
    raise CanaryError(f"不支持的 oracle kind: {oracle['kind']}")


def _run_bound_commands(
    session: Any,
    commands: list[str],
    role: str,
    *,
    require_success: bool,
) -> tuple[bool, list[Any], str]:
    records: list[Any] = []
    last_message = ""
    for command in commands:
        result, message, record = _run_container_bash_impl(
            session=session,
            command=command,
            command_role=role,
            timeout_seconds=AGENT_BUDGET["command_timeout_seconds"],
            workdir="/workspace/repo",
        )
        records.append(record)
        last_message = message
        succeeded = result.exit_code == 0 and not record.timed_out
        if not succeeded:
            if require_success:
                raise CanaryError(f"{role} 冻结命令执行失败")
            return False, records, last_message
    return True, records, last_message


def _select_experiment_build_system(
    session: Any, task: dict[str, Any]
) -> tuple[str, list[str], str]:
    primary, detected, _suggested = inspect_build_system_impl(session=session)
    detected_systems = [system for system, _marker in detected]
    allowed, selected, error = _enforce_experiment_build_system(
        session=session,
        observed_build_system=primary,
        detected_build_systems=detected_systems,
    )
    expected = task["selected_build_system"]
    if not allowed or selected != expected:
        raise CanaryError(error or f"{task['task_id']} build system 漂移")
    return primary, detected_systems, selected


def _inject_fault(
    session: Any, task: dict[str, Any], fault_type: str, ledger: ExperimentLedger
) -> tuple[dict[str, Any], Any]:
    services = get_compile_services()
    mutation_command: str | None = None
    if fault_type == "invalid_build_state":
        invalid_path = (
            "build/Makefile" if task["selected_build_system"] == "cmake" else "Makefile"
        )
        mutation_command = (
            f"test -f {shlex.quote(invalid_path)} && "
            f"printf '%s\\n' all > {shlex.quote(invalid_path)}"
        )
        mutation = "replace_build_state"
        failure_commands = list(task["build_commands"])
    elif fault_type == "missing_compile_input":
        fault_path = task["fault_file"]
        mutation_command = (
            f"test -f {shlex.quote(fault_path)} && rm -- {shlex.quote(fault_path)}"
        )
        mutation = "remove_compile_input"
        failure_commands = list(task["build_commands"])
    elif fault_type == "wrong_build_target":
        mutation = "none"
        failure_commands = [semantic_v2._fault_trigger_command(task, fault_type)]
    else:
        raise CanaryError(f"未知 fault type: {fault_type}")
    if mutation_command is not None:
        mutation_result = services.runtime.exec(
            session,
            mutation_command,
            workdir="/workspace/repo",
            timeout_seconds=30,
            strict_shell=True,
        )
        if mutation_result.exit_code != 0:
            raise CanaryError(f"{task['task_id']} 容器内故障注入失败")
    ledger.append(
        "formal.fault_injected",
        {
            "fault_type": fault_type,
            "mutation": mutation,
            "fault_file": task["fault_file"],
        },
    )
    succeeded, records, message = _run_bound_commands(
        session,
        failure_commands,
        "build",
        require_success=False,
    )
    if succeeded or not records or records[-1].timed_out:
        raise CanaryError(f"{task['task_id']} 未形成有界构建失败")
    state = semantic_v2._state_record(task, fault_type, message[-8_000:])
    ledger.append(
        "formal.fault_observed",
        {
            "state_id": state["state_id"],
            "command_id": records[-1].command_id,
            "exit_code": records[-1].exit_code,
        },
    )
    return state, records[-1]


def _direct_candidate(
    *,
    node_input: AgentBuildNodeInput,
    session: Any,
    manager: Any,
    sequence: int,
    arm: str,
    recipe_records: list[Any],
    supporting_record: Any,
) -> tuple[AgentBuildNodeResult, Path]:
    workflow_dir = (
        Path(session.metadata_path).parent / "agent-workflow" / node_input.attempt_id
    )
    _write_once(workflow_dir / "input.json", node_input.canonical_json())
    ledger = AgentWorkflowEvidenceLedger(
        workflow_dir / "events.jsonl",
        node_input=node_input,
        run_id=session.run_id,
    )
    ledger.append("attempt.registered", input_sha256=node_input.canonical_sha256())
    ledger.append("node.ready")
    ledger.append("node.started", controller="typed_direct_execution")
    state_machine = AgentWorkflowStateMachine()
    state_machine.transition(AgentWorkflowNodeStatus.READY)
    state_machine.transition(AgentWorkflowNodeStatus.RUNNING)
    tracker = AgentWorkflowBudgetTracker(node_input.budget)
    store = AgentWorkflowCandidateStore(state_machine, tracker)
    candidate_path = workflow_dir / "candidate.json"
    service = AgentWorkflowCandidateService(
        node_input=node_input,
        session=session,
        manager=manager,
        store=store,
        candidate_path=candidate_path,
        ledger=ledger,
    )
    target_path, _target_type = _compiled_target(_task(node_input.task_id))
    request = SubmitCandidateRequest(
        candidate_id=f"formal-{sequence:02d}-{arm}-direct",
        build_system=_task(node_input.task_id)["selected_build_system"],
        supporting_command_ids=(supporting_record.command_id,),
        artifact_paths=tuple(_task(node_input.task_id)["target"]["required_artifacts"]),
        target_mapping={node_input.target_contract.target_id: target_path},
        recipe_command_ids=tuple(record.command_id for record in recipe_records),
        agent_summary="Typed route completed through code-bound commands.",
    )
    response = service.submit(request)
    if not response.accepted:
        raise CanaryError(
            f"direct candidate 被拒绝: {','.join(response.rejection_codes)}"
        )
    current = manager.load_session(session.session_id, session.thread_id)
    session.__dict__.update(current.__dict__)
    ledger.append("node.terminal", node_status="submitted", primary_failure=None)
    result = AgentBuildNodeResult(
        node_status="submitted",
        candidate_generated_observed=True,
        candidate_submitted=True,
        submission_id=response.submission_id,
        candidate_record_sha256=response.candidate_record_sha256,
        usage=AgentWorkflowUsage(0, 0, 0, 0, 0),
        wall_clock_ms=0,
        evidence_head_sha256=ledger.head_sha256,
        session_terminal_status=session.status,
    )
    result.validate()
    return result, candidate_path


def _evaluate(
    *,
    node_input: AgentBuildNodeInput,
    node_result: AgentBuildNodeResult,
    session: Any,
    candidate_path: Path,
    evaluation_id: str,
) -> Any:
    services = get_compile_services()
    task = _task(node_input.task_id)
    return run_external_evaluator_v2(
        node_input=node_input,
        node_result=node_result,
        session=session,
        manager=services.manager,
        candidate_path=candidate_path,
        evaluation_id=evaluation_id,
        backend=ForgeCompileEvaluationBackend(
            oracle_registry={_oracle_ref(task): _oracle_spec(task)}
        ),
    )


def _agent_model(thread_id: str) -> Any:
    return agent_runner._create_provider_model(
        {
            "provider_candidate": {
                "profile": AGENT_PROFILE,
                "endpoint": AGENT_ENDPOINT,
                "request_timeout_seconds": AGENT_REQUEST_TIMEOUT_SECONDS,
                "model_max_retries": AGENT_MAX_RETRIES,
            }
        },
        experiment_thread_id=thread_id,
    )


def _agent_token_usage(session: Any, attempt_id: str | None) -> dict[str, int]:
    if session is None or attempt_id is None:
        return {"input_tokens": 0, "output_tokens": 0}
    events_path = (
        Path(session.metadata_path).parent
        / "agent-workflow"
        / attempt_id
        / "events.jsonl"
    )
    if not events_path.is_file():
        return {"input_tokens": 0, "output_tokens": 0}
    input_tokens = 0
    output_tokens = 0
    for line in events_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("event_type") != "model.request_completed":
            continue
        payload = event.get("payload", {})
        input_tokens += int(payload.get("input_tokens", 0))
        output_tokens += int(payload.get("output_tokens", 0))
    return {"input_tokens": input_tokens, "output_tokens": output_tokens}


def _agent_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * AGENT_INPUT_PRICE_USD_PER_MILLION_TOKENS
        + output_tokens * AGENT_OUTPUT_PRICE_USD_PER_MILLION_TOKENS
    ) / 1_000_000


def _arm_directory(sequence: int, task_id: str, arm: str) -> Path:
    return EVIDENCE_ROOT / "arms" / f"{sequence:02d}-{task_id}-{arm}"


def _claim_marker(
    path: Path,
    *,
    manifest_sha256: str,
    release_revision: str,
    sequence: int,
    task_id: str,
    arm: str,
) -> None:
    _write_once_json(
        path,
        {
            "schema_version": "forge-jev-formal-comparison-attempt-5.0.0",
            "identity": IDENTITY,
            "manifest_sha256": manifest_sha256,
            "release_revision": release_revision,
            "sequence": sequence,
            "repetition": _repetition_for_sequence(sequence),
            "task_id": task_id,
            "arm": arm,
            "status": "started",
            "error_class": None,
            "updated_at": _now(),
        },
    )


def _finish_marker(path: Path, *, status: str, error_class: str | None = None) -> None:
    marker = _load_json(path)
    if marker.get("status") != "started":
        raise CanaryError("attempt marker 不处于 started")
    marker["status"] = status
    marker["error_class"] = error_class
    marker["updated_at"] = _now()
    _atomic_json(path, marker)


def _safe_cleanup(session: Any) -> tuple[Any, Any]:
    finalized, cleanup = cleanup_and_finalize_compile_session_impl(session=session)
    agent_runner.require_zero_managed_resources()
    if not cleanup.succeeded or finalized.finalized_at is None:
        raise CanaryError("Compile Session cleanup 或 terminalization 未闭合")
    return finalized, cleanup


async def execute_arm(
    manifest: dict[str, Any],
    *,
    sequence: int,
    task_id: str,
    arm: str,
    release_revision: str,
) -> dict[str, Any]:
    task = _task(task_id)
    case = _case(task_id)
    repetition = _repetition_for_sequence(sequence)
    digest = canonical_sha256(manifest)
    arm_dir = _arm_directory(sequence, task_id, arm)
    marker_path = arm_dir / "attempt.json"
    result_path = arm_dir / "result.json"
    _claim_marker(
        marker_path,
        manifest_sha256=digest,
        release_revision=release_revision,
        sequence=sequence,
        task_id=task_id,
        arm=arm,
    )
    ledger = ExperimentLedger.create(
        arm_dir / "experiment.jsonl",
        experiment_id=new_evidence_id("experiment"),
        physical_attempt_id=new_evidence_id("physical_attempt"),
        context={
            "manifest_sha256": digest,
            "release_revision": release_revision,
            "sequence": sequence,
            "repetition": repetition,
            "task_id": task_id,
            "arm": arm,
        },
    )
    thread_id = f"jev-formal-r{repetition}-{sequence:02d}-{task_id}-{arm}-{digest[:10]}"
    services = get_compile_services()
    session = None
    active = False
    cleanup_succeeded = False
    started = time.perf_counter()
    route_action = "escalate_agent"
    route_observation: dict[str, Any] = {"controller": arm}
    direct_attempted = False
    direct_action_succeeded = False
    escalated = arm == "always_agent"
    jev_requests = 0
    jev_response: dict[str, Any] | None = None
    jev_error_class: str | None = None
    node_result: AgentBuildNodeResult | None = None
    agent_attempt_id: str | None = None
    evaluation = None
    error_class: str | None = None
    finalized = None
    cleanup = None
    initial_command_count = 0
    try:
        activate_experiment(
            thread_id=thread_id,
            experiment_id=ledger.experiment_id,
            physical_attempt_id=ledger.physical_attempt_id,
            ledger=ledger,
            policy=_experiment_policy(manifest, task, arm, sequence),
        )
        active = True
        session = prepare_compile_session_impl(
            thread_id=thread_id,
            repo_url=task["repository_url"],
            run_id=f"jev-formal-r{repetition}-{sequence:02d}-{uuid.uuid4().hex}",
            task_description=f"Jev formal comparison r{repetition} {sequence:02d}: {task_id}/{arm}",
        )
        clone, _message = clone_repository_impl(
            session=session,
            repo_url=task["repository_url"],
            commit_sha=task["commit_sha"],
            depth=1,
            max_retries=1,
        )
        if clone.exit_code != 0 or session.commit_sha != task["commit_sha"]:
            raise CanaryError(f"{task_id} 无法检出冻结 commit")
        primary, detected_systems, selected = _select_experiment_build_system(
            session, task
        )
        route_observation["build_system_detection"] = {
            "primary": primary,
            "detected": detected_systems,
            "selected": selected,
        }
        _configured, baseline_records, _configure_message = _run_bound_commands(
            session,
            list(task["configure_commands"]),
            "configure",
            require_success=True,
        )
        initial_command_count = len(
            services.manager.load_session(
                session.session_id, session.thread_id
            ).commands
        )
        state, failure_record = _inject_fault(session, task, case["fault_type"], ledger)
        route_observation["failure_command_id"] = failure_record.command_id
        route_observation["state_id"] = state["state_id"]

        if arm == "rule_gate_agent":
            route_action = rule_route(state)
            route_observation.update(
                {
                    "selected_action_family": route_action,
                    "disposition": "direct_execute",
                }
            )
        elif arm == "jev_gate_agent":
            jev_requests = 1
            try:
                decision, jev_response = request_jev(state)
                route_action, decision_route = choose_jev_route(state, decision)
                route_observation.update(decision_route)
                route_observation["request_fingerprint"] = decision.request_fingerprint
            except Exception as exc:
                jev_error_class = type(exc).__name__
                route_action = "escalate_agent"
                route_observation.update(
                    {
                        "selected_action_family": route_action,
                        "disposition": "escalate_agent",
                        "reasons": ["jev_provider_or_contract_failure"],
                    }
                )
        elif arm != "always_agent":
            raise CanaryError(f"未知 arm: {arm}")

        if route_action != "escalate_agent":
            direct_attempted = True
            action_succeeded, action_records, _action_message = _run_bound_commands(
                session,
                _commands(task, case["fault_type"], route_action),
                route_action,
                require_success=False,
            )
            direct_action_succeeded = action_succeeded
            if action_succeeded:
                build_records = action_records if route_action == "build" else []
                if route_action != "build":
                    build_succeeded, build_records, _build_message = (
                        _run_bound_commands(
                            session,
                            list(task["build_commands"]),
                            "build",
                            require_success=False,
                        )
                    )
                    action_succeeded = build_succeeded
                stage_records: list[Any] = []
                if action_succeeded:
                    stage_succeeded, stage_records, _stage_message = (
                        _run_bound_commands(
                            session,
                            list(task["artifact_stage_commands"]),
                            "artifact_stage",
                            require_success=False,
                        )
                    )
                    action_succeeded = stage_succeeded
                if action_succeeded:
                    direct_attempt_id = (
                        f"formal-r{repetition}-{sequence:02d}-{arm}-direct"
                    )
                    direct_input = _node_input(
                        manifest,
                        task,
                        session,
                        direct_attempt_id,
                        state,
                        route_observation,
                    )
                    recipe_records = [*baseline_records, *action_records]
                    if route_action != "build":
                        recipe_records.extend(build_records)
                    recipe_records.extend(stage_records)
                    node_result, candidate_path = _direct_candidate(
                        node_input=direct_input,
                        session=session,
                        manager=services.manager,
                        sequence=sequence,
                        arm=arm,
                        recipe_records=recipe_records,
                        supporting_record=build_records[-1],
                    )
                    evaluation = _evaluate(
                        node_input=direct_input,
                        node_result=node_result,
                        session=session,
                        candidate_path=candidate_path,
                        evaluation_id=f"formal-eval-r{repetition}-{sequence:02d}-{arm}-direct",
                    )
                else:
                    escalated = True
            else:
                escalated = True

        if route_action == "escalate_agent" or escalated:
            escalated = True
            agent_attempt_id = f"formal-r{repetition}-{sequence:02d}-{arm}-agent"
            agent_input = _node_input(
                manifest, task, session, agent_attempt_id, state, route_observation
            )
            model = _agent_model(thread_id)
            node_result = await run_agent_workflow_node_v1(
                node_input=agent_input,
                session=session,
                manager=services.manager,
                model=model,
            )
            if node_result.candidate_submitted:
                candidate_path = (
                    Path(session.metadata_path).parent
                    / "agent-workflow"
                    / agent_attempt_id
                    / "candidate.json"
                )
                evaluation = _evaluate(
                    node_input=agent_input,
                    node_result=node_result,
                    session=session,
                    candidate_path=candidate_path,
                    evaluation_id=f"formal-eval-r{repetition}-{sequence:02d}-{arm}-agent",
                )
        finalized, cleanup = _safe_cleanup(session)
        cleanup_succeeded = True
    except BaseException as exc:
        error_class = type(exc).__name__
        if session is not None and not cleanup_succeeded:
            try:
                finalized, cleanup = _safe_cleanup(session)
                cleanup_succeeded = True
            except Exception as cleanup_exc:
                error_class = f"{error_class}+{type(cleanup_exc).__name__}"
                cleanup_succeeded = False
    finally:
        if active:
            deactivate_experiment(thread_id)

    strict_success = bool(
        evaluation is not None and evaluation.strict_reproducible_build_success
    )
    terminal_classification = (
        "arm_error"
        if error_class is not None
        else "strict_success"
        if strict_success
        else "evaluated_failure"
        if evaluation is not None
        else "no_candidate"
    )
    usage = (
        node_result.usage
        if node_result is not None
        else AgentWorkflowUsage(0, 0, 0, 0, 0)
    )
    agent_tokens = _agent_token_usage(session, agent_attempt_id)
    agent_usage = json.loads(json.dumps(asdict(usage)))
    agent_usage.update(agent_tokens)
    agent_usage["estimated_cost_usd"] = _agent_cost_usd(
        agent_tokens["input_tokens"], agent_tokens["output_tokens"]
    )
    if (
        agent_tokens["input_tokens"] + agent_tokens["output_tokens"]
        != usage.recorded_tokens
    ):
        token_error = "AgentTokenAccountingError"
        error_class = f"{error_class}+{token_error}" if error_class else token_error
    jev_usage = (
        jev_response["response"]["usage"]
        if jev_response is not None
        else {"input_tokens": None, "output_tokens": None}
    )
    jev_cost = (
        jev_response["response"]["cost_usd"] if jev_response is not None else None
    )
    final_command_count = (
        len(finalized.commands) if finalized is not None else initial_command_count
    )
    result = {
        "schema_version": "forge-jev-formal-comparison-arm-result-5.0.0",
        "identity": IDENTITY,
        "manifest_sha256": digest,
        "release_revision": release_revision,
        "sequence": sequence,
        "repetition": repetition,
        "task_id": task_id,
        "build_system": task["selected_build_system"],
        "fault_type": case["fault_type"],
        "arm": arm,
        "route": route_observation,
        "route_action": route_action,
        "direct_attempted": direct_attempted,
        "direct_action_succeeded": direct_action_succeeded,
        "escalated_agent": escalated,
        "agent_usage": agent_usage,
        "jev_usage": {
            "model_requests": jev_requests,
            "input_tokens": jev_usage["input_tokens"],
            "output_tokens": jev_usage["output_tokens"],
            "cost_usd": jev_cost,
            "error_class": jev_error_class,
            "response_observed": jev_response is not None,
        },
        "node_status": node_result.node_status if node_result is not None else None,
        "candidate_submitted": node_result.candidate_submitted
        if node_result is not None
        else False,
        "s0_s5": [asdict(layer) for layer in evaluation.layers]
        if evaluation is not None
        else [],
        "strict_reproducible_build_success": strict_success,
        "bitwise_reproducible": evaluation.bitwise_reproducible
        if evaluation is not None
        else None,
        "evaluation_sha256": evaluation.canonical_sha256()
        if evaluation is not None
        else None,
        "session_id": finalized.session_id
        if finalized is not None
        else getattr(session, "session_id", None),
        "session_status": finalized.status
        if finalized is not None
        else getattr(session, "status", None),
        "command_count": final_command_count,
        "cleanup_succeeded": cleanup_succeeded
        and cleanup is not None
        and cleanup.succeeded,
        "zero_managed_resources": cleanup_succeeded,
        "terminal_classification": terminal_classification,
        "error_class": error_class,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "completed_at": _now(),
    }
    _write_once_json(result_path, result)
    ledger.append(
        "experiment.completed",
        {
            "terminal_classification": terminal_classification,
            "strict_success": strict_success,
            "result_sha256": file_sha256(result_path),
        },
    )
    if not cleanup_succeeded:
        _finish_marker(marker_path, status="failed", error_class=error_class)
        raise CanaryError(f"sequence {sequence} cleanup 未闭合")
    _finish_marker(marker_path, status="completed", error_class=error_class)
    return result


def _batch_totals(results: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "agent_requests": sum(row["agent_usage"]["model_requests"] for row in results),
        "agent_recorded_tokens": sum(
            row["agent_usage"]["recorded_tokens"] for row in results
        ),
        "agent_input_tokens": sum(
            row["agent_usage"].get("input_tokens", 0) for row in results
        ),
        "agent_output_tokens": sum(
            row["agent_usage"].get("output_tokens", 0) for row in results
        ),
        "agent_estimated_cost_usd": sum(
            row["agent_usage"].get("estimated_cost_usd", 0.0) for row in results
        ),
        "jev_requests": sum(row["jev_usage"]["model_requests"] for row in results),
        "jev_input_tokens": sum(
            row["jev_usage"]["input_tokens"] or 0 for row in results
        ),
        "jev_cost_usd": sum(row["jev_usage"]["cost_usd"] or 0.0 for row in results),
    }
    totals["total_provider_estimated_cost_usd"] = (
        totals["agent_estimated_cost_usd"] + totals["jev_cost_usd"]
    )
    return totals


def _within_budget(totals: dict[str, Any]) -> bool:
    return (
        totals["agent_requests"] <= TOTAL_AGENT_REQUEST_CEILING
        and totals["agent_recorded_tokens"] <= TOTAL_AGENT_TOKEN_CEILING
        and totals["jev_requests"] <= TOTAL_JEV_REQUEST_CEILING
        and totals["jev_input_tokens"] <= TOTAL_JEV_INPUT_TOKEN_CEILING
        and totals["jev_cost_usd"] <= TOTAL_JEV_COST_CEILING_USD + 1e-12
    )


async def execute_batch() -> dict[str, Any]:
    ready = preflight()
    _qualification_report()
    digest = ready["manifest_sha256"]
    release_revision = ready["git_commit"]
    batch_path = EVIDENCE_ROOT / "batch.json"
    _write_once_json(
        batch_path,
        {
            "schema_version": "forge-jev-formal-comparison-batch-5.0.0",
            "identity": IDENTITY,
            "manifest_sha256": digest,
            "release_revision": release_revision,
            "status": "running",
            "completed_arms": 0,
            "error_class": None,
            "updated_at": _now(),
        },
    )
    results: list[dict[str, Any]] = []
    try:
        for sequence, (task_id, arm) in enumerate(SCHEDULE, start=1):
            result = await execute_arm(
                validate_manifest(),
                sequence=sequence,
                task_id=task_id,
                arm=arm,
                release_revision=release_revision,
            )
            results.append(result)
            totals = _batch_totals(results)
            if not _within_budget(totals):
                raise CanaryError("formal comparison 总预算越界")
            batch = _load_json(batch_path)
            batch["completed_arms"] = len(results)
            batch["totals"] = totals
            batch["updated_at"] = _now()
            _atomic_json(batch_path, batch)
        batch = _load_json(batch_path)
        batch["status"] = "completed"
        batch["updated_at"] = _now()
        _atomic_json(batch_path, batch)
        return batch
    except BaseException as exc:
        batch = _load_json(batch_path)
        batch["status"] = "failed"
        batch["completed_arms"] = len(results)
        batch["totals"] = _batch_totals(results)
        batch["error_class"] = type(exc).__name__
        batch["updated_at"] = _now()
        _atomic_json(batch_path, batch)
        raise


def _evidence_inventory() -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(EVIDENCE_ROOT).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        for path in sorted(EVIDENCE_ROOT.rglob("*"))
        if path.is_file()
    ]


def _percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _provider_cost(row: dict[str, Any]) -> float:
    return float(row["agent_usage"].get("estimated_cost_usd", 0.0)) + float(
        row["jev_usage"].get("cost_usd") or 0.0
    )


def _arm_summary(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    selected = [row for row in rows if row["arm"] == arm]
    return {
        "successes": sum(row["strict_reproducible_build_success"] for row in selected),
        "arms": len(selected),
        "strict_success_rate": (
            statistics.fmean(
                float(row["strict_reproducible_build_success"]) for row in selected
            )
            if selected
            else None
        ),
        "provider_estimated_cost_usd": sum(_provider_cost(row) for row in selected),
        "agent_requests": sum(row["agent_usage"]["model_requests"] for row in selected),
        "agent_recorded_tokens": sum(
            row["agent_usage"]["recorded_tokens"] for row in selected
        ),
        "jev_requests": sum(row["jev_usage"]["model_requests"] for row in selected),
        "rmst_seconds": (
            statistics.fmean(
                min(row["duration_ms"] / 1000, AGENT_BUDGET["node_timeout_seconds"])
                for row in selected
            )
            if selected
            else None
        ),
        "agent_escalations": sum(row["escalated_agent"] for row in selected),
    }


def _clustered_bootstrap(rows: list[dict[str, Any]]) -> dict[str, Any]:
    families = [case["task_id"] for case in CASE_SPECS]
    by_family = {
        family: [row for row in rows if row["task_id"] == family] for family in families
    }
    rng = random.Random(BOOTSTRAP_SEED)
    success_differences: list[float] = []
    cost_reductions: list[float] = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sampled = [rng.choice(families) for _ in families]
        sampled_rows = [row for family in sampled for row in by_family[family]]
        always = _arm_summary(sampled_rows, "always_agent")
        jev = _arm_summary(sampled_rows, "jev_gate_agent")
        if (
            always["strict_success_rate"] is not None
            and jev["strict_success_rate"] is not None
        ):
            success_differences.append(
                jev["strict_success_rate"] - always["strict_success_rate"]
            )
        always_cost = always["provider_estimated_cost_usd"]
        if always_cost > 0:
            cost_reductions.append(1 - jev["provider_estimated_cost_usd"] / always_cost)
    return {
        "unit": "project_family",
        "seed": BOOTSTRAP_SEED,
        "samples": BOOTSTRAP_SAMPLES,
        "strict_success_difference": {
            "one_sided_95_lower": _percentile(success_differences, 0.05),
            "two_sided_95_interval": [
                _percentile(success_differences, 0.025),
                _percentile(success_differences, 0.975),
            ],
        },
        "provider_cost_reduction": {
            "two_sided_95_interval": [
                _percentile(cost_reductions, 0.025),
                _percentile(cost_reductions, 0.975),
            ],
        },
    }


def generate_report() -> dict[str, Any]:
    manifest = validate_manifest()
    validate_parents()
    _qualification_report()
    batch = _load_json(EVIDENCE_ROOT / "batch.json")
    rows: list[dict[str, Any]] = []
    for sequence, (task_id, arm) in enumerate(SCHEDULE, start=1):
        arm_dir = _arm_directory(sequence, task_id, arm)
        marker_path = arm_dir / "attempt.json"
        result_path = arm_dir / "result.json"
        ledger_path = arm_dir / "experiment.jsonl"
        if (
            not marker_path.is_file()
            or not result_path.is_file()
            or not ledger_path.is_file()
        ):
            continue
        marker = _load_json(marker_path)
        result = _load_json(result_path)
        ExperimentLedger.verify_path(ledger_path)
        if (
            marker.get("sequence") != sequence
            or marker.get("repetition") != _repetition_for_sequence(sequence)
            or marker.get("task_id") != task_id
            or marker.get("arm") != arm
        ):
            raise CanaryError("attempt marker schedule 漂移")
        if (
            result.get("sequence") != sequence
            or result.get("repetition") != _repetition_for_sequence(sequence)
            or result.get("task_id") != task_id
            or result.get("arm") != arm
        ):
            raise CanaryError("arm result schedule 漂移")
        rows.append(result)
    totals = _batch_totals(rows)
    agent_runner.require_zero_managed_resources()
    metrics_complete = all(
        isinstance(row.get("agent_usage", {}).get("model_requests"), int)
        and isinstance(row.get("agent_usage", {}).get("recorded_tokens"), int)
        and isinstance(row.get("agent_usage", {}).get("input_tokens"), int)
        and isinstance(row.get("agent_usage", {}).get("output_tokens"), int)
        and isinstance(
            row.get("agent_usage", {}).get("estimated_cost_usd"), (int, float)
        )
        and isinstance(row.get("jev_usage", {}).get("model_requests"), int)
        and isinstance(row.get("duration_ms"), int)
        and isinstance(row.get("escalated_agent"), bool)
        and isinstance(row.get("strict_reproducible_build_success"), bool)
        for row in rows
    )
    jev_usage_complete = all(
        row["arm"] != "jev_gate_agent"
        or (
            (
                row["jev_usage"]["response_observed"] is True
                and isinstance(row["jev_usage"]["input_tokens"], int)
                and isinstance(row["jev_usage"]["cost_usd"], (int, float))
            )
            or isinstance(row["jev_usage"].get("error_class"), str)
        )
        for row in rows
    )
    arm_summaries = {arm: _arm_summary(rows, arm) for arm in ARMS}
    always = arm_summaries["always_agent"]
    jev = arm_summaries["jev_gate_agent"]
    strict_difference = (
        jev["strict_success_rate"] - always["strict_success_rate"]
        if jev["strict_success_rate"] is not None
        and always["strict_success_rate"] is not None
        else None
    )
    cost_reduction = (
        1 - jev["provider_estimated_cost_usd"] / always["provider_estimated_cost_usd"]
        if always["provider_estimated_cost_usd"] > 0
        else None
    )
    bootstrap = _clustered_bootstrap(rows) if len(rows) == len(SCHEDULE) else None
    lower_bound = (
        bootstrap["strict_success_difference"]["one_sided_95_lower"]
        if bootstrap is not None
        else None
    )
    gates = {
        "batch_completed": batch.get("status") == "completed",
        "all_72_arms_classified": len(rows) == len(SCHEDULE)
        and all(row.get("terminal_classification") for row in rows),
        "metrics_complete": metrics_complete and jev_usage_complete,
        "all_cleanup_succeeded": len(rows) == len(SCHEDULE)
        and all(row.get("cleanup_succeeded") is True for row in rows),
        "within_frozen_budget": _within_budget(totals),
        "zero_managed_resources": True,
        "parent_evidence_unchanged": True,
    }
    passed = all(gates.values())
    noninferiority_passed = bool(
        passed and lower_bound is not None and lower_bound >= NONINFERIORITY_MARGIN
    )
    cost_reduction_passed = bool(
        passed
        and cost_reduction is not None
        and cost_reduction >= MINIMUM_COST_REDUCTION
    )
    if not passed:
        decision = "formal_execution_invalid"
    elif noninferiority_passed and cost_reduction_passed:
        decision = "supports_jev_controlled_failure_claim"
    elif not noninferiority_passed:
        decision = "reject_jev_due_to_success_noninferiority"
    else:
        decision = "reject_jev_due_to_cost_reduction"
    direct_rows = [row for row in rows if row["direct_attempted"]]
    wrong_direct = [
        row
        for row in direct_rows
        if row["route_action"] != _case(row["task_id"])["expected_action"]
    ]
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "identity": IDENTITY,
        "manifest_sha256": canonical_sha256(manifest),
        "release_revision": batch.get("release_revision"),
        "created_at": _now(),
        "arm_count": len(rows),
        "rows": rows,
        "totals": totals,
        "arm_summaries": arm_summaries,
        "primary_analysis": {
            "strict_success_rate_difference": strict_difference,
            "noninferiority_margin": NONINFERIORITY_MARGIN,
            "noninferiority_passed": noninferiority_passed,
            "provider_cost_reduction": cost_reduction,
            "minimum_provider_cost_reduction": MINIMUM_COST_REDUCTION,
            "cost_reduction_passed": cost_reduction_passed,
            "clustered_bootstrap": bootstrap,
        },
        "by_build_system": {
            build_system: {
                arm: _arm_summary(
                    [row for row in rows if row["build_system"] == build_system], arm
                )
                for arm in ARMS
            }
            for build_system in ("cmake", "make", "autotools")
        },
        "routing": {
            "direct_attempts": len(direct_rows),
            "direct_action_failures": sum(
                row["direct_attempted"] and not row["direct_action_succeeded"]
                for row in rows
            ),
            "wrong_direct_actions": len(wrong_direct),
            "wrong_direct_action_rate": (
                len(wrong_direct) / len(direct_rows) if direct_rows else None
            ),
            "agent_escalations": sum(row["escalated_agent"] for row in rows),
            "agent_escalation_rate": (
                sum(row["escalated_agent"] for row in rows) / len(rows)
                if rows
                else None
            ),
        },
        "gates": gates,
        "passed": passed,
        "decision": decision,
        "interpretation": manifest["interpretation"],
        "evidence_inventory": _evidence_inventory(),
    }
    if JSON_REPORT_PATH.exists() or MARKDOWN_REPORT_PATH.exists():
        raise CanaryError("formal report 已存在")
    _write_once_json(JSON_REPORT_PATH, report)
    strict_lines = "\n".join(
        f"- `{arm}`：{values['successes']}/{values['arms']} strict success"
        for arm, values in report["arm_summaries"].items()
    )
    lower_text = "NA" if lower_bound is None else f"{lower_bound:.3f}"
    reduction_text = "NA" if cost_reduction is None else f"{cost_reduction:.1%}"
    _write_once(
        MARKDOWN_REPORT_PATH,
        "# Jev 未见项目族正式三臂比较 v5\n\n"
        f"- 决定：`{report['decision']}`\n"
        f"- 完整 arm：`{report['arm_count']}/{len(SCHEDULE)}`\n"
        f"- Agent 请求 / tokens：`{totals['agent_requests']} / {totals['agent_recorded_tokens']}`\n"
        f"- Jev 请求 / input tokens / 费用：`{totals['jev_requests']} / {totals['jev_input_tokens']} / ${totals['jev_cost_usd']:.8f}`\n"
        f"- Provider 保守估算总费用：`${totals['total_provider_estimated_cost_usd']:.6f}`\n"
        f"- strict 差值单侧 95% 下界：`{lower_text}`，门槛 `{NONINFERIORITY_MARGIN:.3f}`\n"
        f"- Jev 相对 AlwaysAgent 成本下降：`{reduction_text}`，门槛 `{MINIMUM_COST_REDUCTION:.0%}`\n"
        f"- 直接动作 / 错误直接动作 / Agent 升级：`{report['routing']['direct_attempts']} / {report['routing']['wrong_direct_actions']} / {report['routing']['agent_escalations']}`\n\n"
        "## 严格终点\n\n"
        f"{strict_lines}\n\n"
        "## 解释边界\n\n"
        "本结果只覆盖冻结的受控构建失败和当前未见项目族。Provider 费用按冻结的 peak/cache-miss "
        "价目表保守估算；结果不支持自然失败泛化、通用模型排名或动态预算优越性。\n",
    )
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    bind = sub.add_parser("bind")
    bind.add_argument("--implementation-revision", required=True)
    sub.add_parser("validate")
    sub.add_parser("preflight")
    sub.add_parser("qualify")
    sub.add_parser("run")
    sub.add_parser("report")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "bind":
        print(
            json.dumps(
                bind_identity(args.implementation_revision),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    elif args.command == "validate":
        print(
            json.dumps(
                validate_manifest(), ensure_ascii=False, indent=2, sort_keys=True
            )
        )
    elif args.command == "preflight":
        print(json.dumps(preflight(), ensure_ascii=False, indent=2, sort_keys=True))
    elif args.command == "qualify":
        print(
            json.dumps(
                zero_provider_qualification(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    elif args.command == "run":
        print(
            json.dumps(
                asyncio.run(execute_batch()),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    elif args.command == "report":
        print(
            json.dumps(generate_report(), ensure_ascii=False, indent=2, sort_keys=True)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

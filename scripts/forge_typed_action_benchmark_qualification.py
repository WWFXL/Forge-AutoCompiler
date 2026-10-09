#!/usr/bin/env python3
"""Issue #389 Jev 类型化动作 benchmark 的零 Provider 资格审计。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import jsonschema

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
IDENTITY = "cpp-typed-action-benchmark-qualification-v1"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/389"
SCHEMA_VERSION = "forge-typed-action-benchmark-qualification-1.0.1"
REPORT_SCHEMA_VERSION = "forge-typed-action-benchmark-qualification-report-1.0.0"

DEFAULT_SOURCE_POOL = REPO_ROOT / "benchmarks/fixtures/cpp-typed-action-benchmark-source-pool-v1.json"
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-typed-action-benchmark-qualification-v1.json"
DEFAULT_SCHEMA = REPO_ROOT / "benchmarks/schemas/forge-typed-action-benchmark-qualification-v1.schema.json"
DEFAULT_JSON_REPORT = REPO_ROOT / "benchmarks/reports/cpp-typed-action-benchmark-qualification-v1.json"
DEFAULT_MARKDOWN_REPORT = REPO_ROOT / "benchmarks/reports/cpp-typed-action-benchmark-qualification-v1.md"
DEFAULT_RULE_GATE_JSON = REPO_ROOT / "benchmarks/reports/cpp-typed-action-benchmark-rule-gate-audit-v1.json"
DEFAULT_RULE_GATE_MARKDOWN = REPO_ROOT / "benchmarks/reports/cpp-typed-action-benchmark-rule-gate-audit-v1.md"
PREREGISTRATION = REPO_ROOT / "benchmarks/preregistrations/cpp-typed-action-benchmark-qualification-v1.md"
ATTEMPT_1_FAILURE = REPO_ROOT / "benchmarks/reports/cpp-typed-action-benchmark-qualification-v1-attempt-1-failure.json"
STAGE_C_POOL = REPO_ROOT / "benchmarks/fixtures/stage-c-source-pool.json"
STAGE_C_PLAN = REPO_ROOT / "benchmarks/manifests/cpp-stage-c-task-qualification.json"
HISTORICAL_MANIFEST = REPO_ROOT / "benchmarks/manifests/cpp-cross-build-progress-state-qualification-v1.json"
HISTORICAL_REPORT = REPO_ROOT / "benchmarks/reports/cpp-cross-build-progress-state-qualification-v1.json"
SESSIONS_ROOT = REPO_ROOT / ".compile-sessions"

BUILD_SYSTEMS = ("cmake", "make", "autotools")
SPLITS = ("design", "calibration", "evaluation")
ACTION_FAMILIES = (
    "dependency",
    "configure",
    "build",
    "diagnostic_probe",
    "smoke",
    "artifact_stage",
    "submit",
    "escalate_agent",
)
STATE_KINDS = ("source_ready", "configured_or_ready", "build_failed", "built", "staged")
MANAGED_PREFIX = "forge-typed-action-q-"
IMAGE_LABEL = "org.forge-autocompiler.stage-c.dockerfile-sha256"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_LOG_BYTES = 4096


class QualificationError(RuntimeError):
    """资格合同、输入、执行环境或结果不满足冻结要求。"""


COMMIT_TIMES = {
    "leveldb": "2026-03-10T21:06:29-07:00",
    "libjpeg-turbo": "2026-09-24T12:07:01-04:00",
    "libsoundio": "2023-07-05T18:55:18-07:00",
    "oatpp": "2025-11-12T08:19:27+02:00",
    "8cc": "2020-10-13T11:02:56+09:00",
    "stockfish-11": "2020-01-18T01:44:37+01:00",
    "lz4": "2026-06-01T15:21:37-07:00",
    "rnnoise-0.1.1": "2024-03-22T17:44:13-04:00",
    "theora": "2026-05-11T02:27:30+00:00",
    "libsndfile": "2026-09-01T19:08:11+10:00",
    "civetweb": "2026-04-19T17:04:45+02:00",
    "json-c": "2026-09-20T16:06:05-04:00",
}

SPLIT_MEMBERS = {
    "design": (
        "stockfish-11",
        "libsoundio",
        "rnnoise-0.1.1",
        "leveldb",
        "lz4",
        "jansson",
    ),
    "calibration": ("8cc", "oatpp", "libogg", "civetweb", "theora", "libyaml"),
    "evaluation": (
        "libevent",
        "libtomcrypt",
        "libsndfile",
        "cjson",
        "xxhash",
        "json-c",
        "libjpeg-turbo",
        "zstd",
        "libuv",
        "pugixml",
        "fmt",
        "openh264",
    ),
}


def _task(
    *,
    task_id: str,
    repository_url: str,
    commit_sha: str,
    commit_committed_at: str,
    source_snapshot_sha256: str,
    license_path: str,
    license_sha256: str,
    build_system: str,
    configure_commands: list[str],
    build_commands: list[str],
    artifact_stage_commands: list[str],
    required_artifacts: list[str],
    artifact_types: list[str],
    oracle: dict[str, Any],
    tracked_file_count: int,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "repository_url": repository_url,
        "commit_sha": commit_sha,
        "commit_committed_at": commit_committed_at,
        "source_snapshot_sha256": source_snapshot_sha256,
        "license_path": license_path,
        "license_sha256": license_sha256,
        "submodule_commits": {},
        "selected_build_system": build_system,
        "tracked_file_count": tracked_file_count,
        "configure_commands": configure_commands,
        "build_commands": build_commands,
        "artifact_stage_commands": artifact_stage_commands,
        "target": {
            "required_artifacts": required_artifacts,
            "artifact_types": artifact_types,
            "bitwise_required": "executable" not in artifact_types,
        },
        "oracle": oracle,
    }


NEW_TASKS = (
    _task(
        task_id="cjson",
        repository_url="https://github.com/DaveGamble/cJSON.git",
        commit_sha="6d9f2443ab071f86e5d9b43025a40929ec41c46c",
        commit_committed_at="2026-09-16T09:55:35+08:00",
        source_snapshot_sha256="ec38c5916785f16394225fb3f6246e2a15a235a856ecf03800828e1baf0c8031",
        license_path="LICENSE",
        license_sha256="a36dda207c36db5818729c54e7ad4e8b0c6fba847491ba64f372c1a2037b6d5c",
        build_system="cmake",
        configure_commands=["cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/artifacts -DENABLE_CJSON_TEST=OFF -DENABLE_CJSON_UTILS=OFF -DBUILD_SHARED_LIBS=OFF"],
        build_commands=["cmake --build build --parallel 4"],
        artifact_stage_commands=["cmake --install build"],
        required_artifacts=["include/cjson/cJSON.h", "lib/libcjson.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": '#include <cjson/cJSON.h>\nint main(void){ cJSON *v=cJSON_Parse("{\\"x\\":1}"); if(!v) return 1; cJSON_Delete(v); return 0; }\n',
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libcjson.a",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=229,
    ),
    _task(
        task_id="pugixml",
        repository_url="https://github.com/zeux/pugixml.git",
        commit_sha="61421263d199c749b21fb1907b23d79ddd8285a1",
        commit_committed_at="2026-10-08T00:01:57-07:00",
        source_snapshot_sha256="e52b0f28fee758e4e7a6cb3861641431ccc5839bb52798f5695544514edfe9cf",
        license_path="LICENSE.md",
        license_sha256="90974fbb120e966b452654eaae3ba6ee55f3647db3b28918a7649733ee99da97",
        build_system="cmake",
        configure_commands=["cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/artifacts -DPUGIXML_BUILD_TESTS=OFF -DBUILD_SHARED_LIBS=OFF"],
        build_commands=["cmake --build build --parallel 4"],
        artifact_stage_commands=["cmake --install build"],
        required_artifacts=["include/pugixml.hpp", "lib/libpugixml.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c++17",
            "source": '#include <pugixml.hpp>\nint main(){ pugi::xml_document d; return d.load_string("<x/>") ? 0 : 1; }\n',
            "compile_argv": [
                "c++",
                "-std=c++17",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libpugixml.a",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=191,
    ),
    _task(
        task_id="fmt",
        repository_url="https://github.com/fmtlib/fmt.git",
        commit_sha="35c58f084e7cd79b51997439cff68346f4c724c0",
        commit_committed_at="2026-10-08T13:06:28-07:00",
        source_snapshot_sha256="043285960b64a33d13fed19a4671227d88aef95fbb3cbf32e838bd2097d8a359",
        license_path="LICENSE",
        license_sha256="a65fcc5a1095fc33cc37e4fff69366e49d7e92f613558a2b95ed1b70e33758b4",
        build_system="cmake",
        configure_commands=["cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/artifacts -DFMT_TEST=OFF -DFMT_DOC=OFF -DFMT_INSTALL=ON -DBUILD_SHARED_LIBS=OFF"],
        build_commands=["cmake --build build --parallel 4"],
        artifact_stage_commands=["cmake --install build"],
        required_artifacts=["include/fmt/format.h", "lib/libfmt.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c++17",
            "source": '#include <fmt/format.h>\nint main(){ return fmt::format("{}", 7)=="7" ? 0 : 1; }\n',
            "compile_argv": [
                "c++",
                "-std=c++17",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libfmt.a",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=145,
    ),
    _task(
        task_id="libtomcrypt",
        repository_url="https://github.com/libtom/libtomcrypt.git",
        commit_sha="6c6d5104de66f3ca0dfd7b68540ef86869982b07",
        commit_committed_at="2026-09-01T14:17:58+02:00",
        source_snapshot_sha256="e27383f400dc997bd5674bf66bc06154b51a8653c27ad57297c0986b1f6ea3fc",
        license_path="LICENSE",
        license_sha256="2fa64b163659f41965c9815882a8296d3d03ff546b76153e11445f9bdecf955a",
        build_system="make",
        configure_commands=[],
        build_commands=["make -j4 library"],
        artifact_stage_commands=["mkdir -p /artifacts/lib /artifacts/include && cp libtomcrypt.a /artifacts/lib/libtomcrypt.a && cp -a src/headers/. /artifacts/include/"],
        required_artifacts=["include/tomcrypt.h", "lib/libtomcrypt.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <tomcrypt.h>\nint main(void){ return register_hash(&sha256_desc) >= 0 ? 0 : 1; }\n",
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libtomcrypt.a",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=1052,
    ),
    _task(
        task_id="xxhash",
        repository_url="https://github.com/Cyan4973/xxHash.git",
        commit_sha="680bf463fa1ca0461b9a7c2dab7556e1f54cf4cf",
        commit_committed_at="2026-09-19T22:53:15-07:00",
        source_snapshot_sha256="dc406b7d480d7708d1bf77bf1c1e7f898d1a5da06f438aa343dae5946c5b17d3",
        license_path="LICENSE",
        license_sha256="6ffedbc0f7878612d2b23589f1ff2ab15633e1df7963a5d9fc750ec5500c7e7a",
        build_system="make",
        configure_commands=[],
        build_commands=["make -j4 lib"],
        artifact_stage_commands=["mkdir -p /artifacts/lib /artifacts/include && cp libxxhash.a /artifacts/lib/libxxhash.a && cp xxhash.h /artifacts/include/xxhash.h"],
        required_artifacts=["include/xxhash.h", "lib/libxxhash.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": '#include <xxhash.h>\nint main(void){ return XXH64("forge",5,0) ? 0 : 1; }\n',
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libxxhash.a",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=101,
    ),
    _task(
        task_id="zstd",
        repository_url="https://github.com/facebook/zstd.git",
        commit_sha="49cf51799ea051457f57243527aa2058f999f005",
        commit_committed_at="2026-10-05T18:11:50-07:00",
        source_snapshot_sha256="4757b5ad42b146f39c370bcd7ee6390e6ff188bbd414daa6897fa5c5b4c5d9f6",
        license_path="LICENSE",
        license_sha256="7055266497633c9025b777c78eb7235af13922117480ed5c674677adc381c9d8",
        build_system="make",
        configure_commands=[],
        build_commands=["make -C lib -j4 libzstd.a"],
        artifact_stage_commands=["mkdir -p /artifacts/lib /artifacts/include && cp lib/libzstd.a /artifacts/lib/libzstd.a && cp lib/zstd.h lib/zdict.h lib/zstd_errors.h /artifacts/include/"],
        required_artifacts=["include/zstd.h", "lib/libzstd.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <zstd.h>\nint main(void){ return ZSTD_versionNumber() > 0 ? 0 : 1; }\n",
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libzstd.a",
                "-pthread",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=662,
    ),
    _task(
        task_id="openh264",
        repository_url="https://github.com/cisco/openh264.git",
        commit_sha="6fe62b8f3fcc6bf34512be7efc7f64e91f510f02",
        commit_committed_at="2026-10-09T16:06:24+08:00",
        source_snapshot_sha256="ca8df42586a47c211b43a963b140e3f2beaf8e24b5a9986f29a47f81d03a9499",
        license_path="LICENSE",
        license_sha256="dd5c1c9668512530fa5a96e4c29ac4033d70a7eeb0eed7a42fddb6dd794ebdbb",
        build_system="make",
        configure_commands=[],
        build_commands=["make -j4 libraries"],
        artifact_stage_commands=["mkdir -p /artifacts/lib /artifacts/include/wels && cp libopenh264.a /artifacts/lib/libopenh264.a && cp codec/api/wels/*.h /artifacts/include/wels/"],
        required_artifacts=["include/wels/codec_api.h", "lib/libopenh264.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c++17",
            "source": "#include <wels/codec_api.h>\nint main(){ ISVCEncoder *e=nullptr; if(WelsCreateSVCEncoder(&e)!=0 || !e) return 1; WelsDestroySVCEncoder(e); return 0; }\n",
            "compile_argv": [
                "c++",
                "-std=c++17",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libopenh264.a",
                "-pthread",
                "-lm",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=742,
    ),
    _task(
        task_id="libyaml",
        repository_url="https://github.com/yaml/libyaml.git",
        commit_sha="90a56d4500aa1a1798514c5cb55c3ad4cb095f94",
        commit_committed_at="2026-08-21T14:12:42-04:00",
        source_snapshot_sha256="2b37373e4dca9d599e74f3e330d799f91881aabf114a146f505d3bd4d0c4a4ca",
        license_path="License",
        license_sha256="c40112449f254b9753045925248313e9270efa36d226b22d82d4cc6c43c57f29",
        build_system="autotools",
        configure_commands=[
            "autoreconf -fi",
            "./configure --prefix=/artifacts --disable-shared",
        ],
        build_commands=["make -j4"],
        artifact_stage_commands=["make install"],
        required_artifacts=["include/yaml.h", "lib/libyaml.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <yaml.h>\nint main(void){ yaml_parser_t p; if(!yaml_parser_initialize(&p)) return 1; yaml_parser_delete(&p); return 0; }\n",
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libyaml.a",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=70,
    ),
    _task(
        task_id="jansson",
        repository_url="https://github.com/akheron/jansson.git",
        commit_sha="851a2145e3256f2e67e5dfe24b0e456bf198b741",
        commit_committed_at="2026-07-09T20:43:34+03:00",
        source_snapshot_sha256="a2ea0993f0afd2fc9d28186ee0a0e8884a29ed0aaa63b11b10d3f002061a2e7b",
        license_path="LICENSE",
        license_sha256="150d90904cd8de73609bb177b42edd3867b07b4b7b786dbba319f30de39fcda2",
        build_system="autotools",
        configure_commands=[
            "autoreconf -fi",
            "./configure --prefix=/artifacts --disable-shared",
        ],
        build_commands=["make -j4"],
        artifact_stage_commands=["make install"],
        required_artifacts=["include/jansson.h", "lib/libjansson.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <jansson.h>\nint main(void){ json_t *v=json_integer(7); if(!v) return 1; json_decref(v); return 0; }\n",
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libjansson.a",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=369,
    ),
    _task(
        task_id="libevent",
        repository_url="https://github.com/libevent/libevent.git",
        commit_sha="d82464a277d0f42703702c4dfd9af6af38595a83",
        commit_committed_at="2026-08-29T15:34:26-07:00",
        source_snapshot_sha256="b574b21eaac116b5791a167a750898f922ce24677c7f60d2da9fd37c237c5e10",
        license_path="LICENSE",
        license_sha256="75092d5ecfeefefacc0f345b6f0172234ca580c279c537de7229597cfbfd71e7",
        build_system="autotools",
        configure_commands=[
            "./autogen.sh",
            "./configure --prefix=/artifacts --disable-shared --disable-openssl --disable-libevent-regress",
        ],
        build_commands=["make -j4"],
        artifact_stage_commands=["make install"],
        required_artifacts=["include/event2/event.h", "lib/libevent.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <event2/event.h>\nint main(void){ struct event_base *b=event_base_new(); if(!b) return 1; event_base_free(b); return 0; }\n",
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libevent.a",
                "-pthread",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=266,
    ),
    _task(
        task_id="libuv",
        repository_url="https://github.com/libuv/libuv.git",
        commit_sha="eb497c582f5c0887add4d4658c7801e4ef412e10",
        commit_committed_at="2026-10-07T21:19:22+02:00",
        source_snapshot_sha256="87f9fc85b0ac7917f08617bf87d9f8824d28f216401fe8a2315c90435eaea999",
        license_path="LICENSE",
        license_sha256="16de0c32b265cb7d46a6d3bd614f259dd4d693a5e26b3407b04aae8d73041f0c",
        build_system="autotools",
        configure_commands=[
            "./autogen.sh",
            "./configure --prefix=/artifacts --disable-shared",
        ],
        build_commands=["make -j4"],
        artifact_stage_commands=["make install"],
        required_artifacts=["include/uv.h", "lib/libuv.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <uv.h>\nint main(void){ uv_loop_t loop; if(uv_loop_init(&loop)) return 1; return uv_loop_close(&loop); }\n",
            "compile_argv": [
                "cc",
                "-std=gnu11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libuv.a",
                "-pthread",
                "-ldl",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=483,
    ),
    _task(
        task_id="libogg",
        repository_url="https://github.com/xiph/ogg.git",
        commit_sha="06a5e0262cdc28aa4ae6797627a783b5010440f0",
        commit_committed_at="2026-03-02T05:10:35-08:00",
        source_snapshot_sha256="ec48ebf0de5430d125dba13cabc36c4141623d345457378a67da184669dbbe16",
        license_path="COPYING",
        license_sha256="d2ab5758336489da61c12cc5bb757da5339c4ae9001f9bb0562b4370249af814",
        build_system="autotools",
        configure_commands=[
            "./autogen.sh",
            "./configure --prefix=/artifacts --disable-shared",
        ],
        build_commands=["make -j4"],
        artifact_stage_commands=["make install"],
        required_artifacts=["include/ogg/ogg.h", "lib/libogg.a"],
        artifact_types=["support_file", "static_library"],
        oracle={
            "kind": "compile_and_run",
            "language": "c11",
            "source": "#include <ogg/ogg.h>\nint main(void){ ogg_sync_state s; if(ogg_sync_init(&s)) return 1; return ogg_sync_clear(&s); }\n",
            "compile_argv": [
                "cc",
                "-std=c11",
                "-I/artifacts/include",
                "{source}",
                "/artifacts/lib/libogg.a",
                "-o",
                "{executable}",
            ],
            "run_argv": ["{executable}"],
        },
        tracked_file_count=125,
    ),
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualificationError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise QualificationError(f"JSON 顶层必须为对象: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_once(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def normalize_project_family(repository_url: str) -> str:
    parsed = urlparse(repository_url)
    parts = [part for part in parsed.path.strip("/").removesuffix(".git").split("/") if part]
    if parsed.scheme != "https" or not parsed.hostname or len(parts) != 2 or "@" in repository_url:
        raise QualificationError(f"repository_url 不是无凭据 HTTPS owner/repo: {repository_url}")
    return f"{parsed.hostname.lower()}/{parts[0].lower()}/{parts[1].lower()}"


def _split_for(task_id: str) -> str:
    matches = [split for split, members in SPLIT_MEMBERS.items() if task_id in members]
    if len(matches) != 1:
        raise QualificationError(f"{task_id} 未唯一分配到 split")
    return matches[0]


def _existing_tasks() -> list[dict[str, Any]]:
    pool = load_json(STAGE_C_POOL)
    plan = load_json(STAGE_C_PLAN)
    plan_by_id = {task["task_id"]: task for task in plan["tasks"]}
    tasks: list[dict[str, Any]] = []
    for source in pool["tasks"]:
        task_id = source["task_id"]
        qualification = plan_by_id[task_id]
        recipe = qualification["reference_recipe"]
        build_system = source["selected_build_system"]
        if build_system == "cmake":
            configure_commands, build_commands, stage_commands = (
                recipe[:1],
                recipe[1:2],
                recipe[2:],
            )
        elif build_system == "autotools":
            configure_commands, build_commands, stage_commands = (
                recipe[:2],
                recipe[2:3],
                recipe[3:],
            )
        elif task_id == "civetweb":
            configure_commands, build_commands, stage_commands = (
                recipe[:1],
                recipe[1:2],
                recipe[2:],
            )
        else:
            configure_commands, build_commands, stage_commands = (
                [],
                recipe[:1],
                recipe[1:],
            )
        tasks.append(
            {
                "task_id": task_id,
                "repository_url": source["repository_url"],
                "commit_sha": source["commit_sha"],
                "commit_committed_at": COMMIT_TIMES[task_id],
                "source_snapshot_sha256": source["source_snapshot_sha256"],
                "license_path": source["license_path"],
                "license_sha256": source["license_sha256"],
                "submodule_commits": source["submodule_commits"],
                "selected_build_system": build_system,
                "tracked_file_count": source["tracked_file_count"],
                "configure_commands": configure_commands,
                "build_commands": build_commands,
                "artifact_stage_commands": stage_commands,
                "target": {
                    "required_artifacts": qualification["target"]["required_artifacts"],
                    "artifact_types": qualification["target"]["artifact_types"],
                    "bitwise_required": qualification["target"]["bitwise_required"],
                },
                "oracle": qualification["oracle"],
            }
        )
    return tasks


def generate_source_pool() -> dict[str, Any]:
    by_id = {task["task_id"]: task for task in [*_existing_tasks(), *NEW_TASKS]}
    ordered_ids = [task_id for split in SPLITS for task_id in SPLIT_MEMBERS[split]]
    tasks = []
    for task_id in ordered_ids:
        task = dict(by_id[task_id])
        task["split"] = _split_for(task_id)
        task["project_family"] = normalize_project_family(task["repository_url"])
        tasks.append(task)
    return {
        "schema_version": "forge-typed-action-source-pool-1.0.1",
        "document_type": "forge_typed_action_source_pool",
        "identity": IDENTITY,
        "selection_frozen_at": "2026-10-09T18:30:00+08:00",
        "temporal_rule": {
            "kind": "strict_commit_time_separation",
            "development_splits": ["design", "calibration"],
            "latest_development_commit": "2026-08-21T14:12:42-04:00",
            "earliest_evaluation_commit": "2026-08-29T15:34:26-07:00",
        },
        "quotas": {
            "project_count": 24,
            "split": {"design": 6, "calibration": 6, "evaluation": 12},
            "build_system": {"cmake": 8, "make": 8, "autotools": 8},
        },
        "selection_notes": {
            "existing_qualified_source_pool": STAGE_C_POOL.relative_to(REPO_ROOT).as_posix(),
            "historical_results_imported": False,
            "replacement_after_benchmark_outcome": False,
            "catalog_unavailable": "seclab-fudan/CXXCrafter-Community-Edition@bac70e99e48b210a350c18b3f93efd839787ce37 was unavailable during selection",
            "excluded_candidates": [
                {
                    "task_id": "libffi",
                    "repository_url": "https://github.com/libffi/libffi.git",
                    "commit_sha": "bc553867367246d140cd156f060bd0409f57f157",
                    "reason": "fixed image autoreconf failed because LT_SYS_SYMBOL_USCORE was undefined",
                    "replacement_task_id": "libuv",
                    "outcome_observed_before_replacement": False,
                }
            ],
        },
        "amendments": [
            {
                "amendment": 1,
                "reason": "libuv oracle compile contract hid pthread declarations under strict c11",
                "sole_change": "libuv oracle compile flag -std=c11 -> -std=gnu11",
                "reuse_partial_outcomes": False,
            }
        ],
        "tasks": tasks,
    }


def _action_catalog() -> dict[str, Any]:
    return {
        "families": list(ACTION_FAMILIES),
        "generation": "code_bound_closed_set",
        "shell_generation_by_model": False,
        "candidate_count_per_state": 3,
        "direct_execution_definition": "execute_bound_action_without_full_agent_reasoning",
        "strict_endpoints_never_skipped": [
            "candidate_verifier",
            "functional_oracle",
            "provenance",
            "clean_replay",
        ],
    }


def generate_manifest(source_pool: dict[str, Any] | None = None) -> dict[str, Any]:
    pool = source_pool or generate_source_pool()
    return {
        "$schema": "../schemas/forge-typed-action-benchmark-qualification-v1.schema.json",
        "schema_version": SCHEMA_VERSION,
        "document_type": "forge_typed_action_benchmark_qualification",
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "status": "authorized_zero_provider_qualification",
        "authorization": {
            "provider_calls_authorized": False,
            "credential_read_authorized": False,
            "model_calls_authorized": False,
            "model_tokens_authorized": 0,
            "reference_clone_authorized": True,
            "docker_action_execution_authorized": True,
            "new_identity_evidence_write_authorized": True,
            "historical_evidence_write_authorized": False,
            "controller_implementation_authorized": False,
        },
        "source_pool": {
            "path": DEFAULT_SOURCE_POOL.relative_to(REPO_ROOT).as_posix(),
            "canonical_sha256": canonical_sha256(pool),
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
            "states_per_project": 5,
            "state_kinds": list(STATE_KINDS),
            "candidate_actions_per_state": 3,
            "outcome_source": "isolated_candidate_execution",
            "old_agent_action_is_ground_truth": False,
            "action_catalog": _action_catalog(),
        },
        "historical_coverage_audit": {
            "manifest_path": HISTORICAL_MANIFEST.relative_to(REPO_ROOT).as_posix(),
            "manifest_sha256": file_sha256(HISTORICAL_MANIFEST),
            "report_path": HISTORICAL_REPORT.relative_to(REPO_ROOT).as_posix(),
            "report_sha256": file_sha256(HISTORICAL_REPORT),
            "expected_eligible_decisions": 409,
            "read_only": True,
            "counterfactual_outcomes_read": False,
        },
        "qualification_thresholds": {
            "project_count": 24,
            "projects_per_build_system": 8,
            "design_projects": 6,
            "calibration_projects": 6,
            "evaluation_projects": 12,
            "states_per_project": 5,
            "minimum_states_per_action_family": 20,
            "minimum_replay_consistency": 0.95,
            "minimum_historical_catalog_coverage": 0.30,
            "require_all_build_systems_complete": True,
        },
        "decision_rule": {
            "pass": "proceed_to_jev_offline_qualification",
            "fail": "abandon_controller_and_keep_benchmark",
            "threshold_adjustment_after_results": False,
        },
        "amendments": [
            {
                "amendment": 1,
                "failed_attempt": 1,
                "failure_record_path": ATTEMPT_1_FAILURE.relative_to(REPO_ROOT).as_posix(),
                "failure_record_sha256": file_sha256(ATTEMPT_1_FAILURE),
                "fresh_full_rerun_required": True,
                "sole_change": "libuv oracle compile flag -std=c11 -> -std=gnu11",
                "project_replacement": False,
                "threshold_change": False,
                "action_schema_change": False,
            }
        ],
        "outputs": {
            "json_report": DEFAULT_JSON_REPORT.relative_to(REPO_ROOT).as_posix(),
            "markdown_report": DEFAULT_MARKDOWN_REPORT.relative_to(REPO_ROOT).as_posix(),
        },
    }


def generate_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/WWFXL/Forge-AutoCompiler/benchmarks/schemas/forge-typed-action-benchmark-qualification-v1.schema.json",
        "title": "Forge typed action benchmark qualification v1",
        "const": manifest,
    }


def _safe_relative(value: str) -> None:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise QualificationError(f"不安全的相对路径: {value}")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise QualificationError(f"时间缺少时区: {value}")
    return parsed


def validate_source_pool(pool: dict[str, Any]) -> dict[str, Any]:
    if pool.get("schema_version") != "forge-typed-action-source-pool-1.0.1" or pool.get("identity") != IDENTITY:
        raise QualificationError("source pool identity 无效")
    tasks = pool.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 24:
        raise QualificationError("source pool 必须包含 24 个项目")
    ids = [task.get("task_id") for task in tasks]
    families = [task.get("project_family") for task in tasks]
    if len(set(ids)) != 24 or len(set(families)) != 24:
        raise QualificationError("task_id 或 project family 未完全隔离")
    if Counter(task.get("split") for task in tasks) != Counter(pool["quotas"]["split"]):
        raise QualificationError("split 配额漂移")
    if Counter(task.get("selected_build_system") for task in tasks) != Counter(pool["quotas"]["build_system"]):
        raise QualificationError("build system 配额漂移")
    forbidden = ("curl ", "wget ", "git clone", "git fetch", "apt-get", "apt ")
    for task in tasks:
        if task["project_family"] != normalize_project_family(task["repository_url"]):
            raise QualificationError(f"{task['task_id']} project family 漂移")
        if not isinstance(task.get("commit_sha"), str) or HEX40.fullmatch(task["commit_sha"]) is None:
            raise QualificationError(f"{task['task_id']} exact commit 无效")
        if HEX64.fullmatch(str(task.get("source_snapshot_sha256", ""))) is None or HEX64.fullmatch(str(task.get("license_sha256", ""))) is None:
            raise QualificationError(f"{task['task_id']} source/license identity 无效")
        _safe_relative(task["license_path"])
        target = task.get("target", {})
        if len(target.get("required_artifacts", [])) != len(target.get("artifact_types", [])) or not target.get("required_artifacts"):
            raise QualificationError(f"{task['task_id']} target 无效")
        for relative in target["required_artifacts"]:
            _safe_relative(relative)
        commands = [
            *task["configure_commands"],
            *task["build_commands"],
            *task["artifact_stage_commands"],
        ]
        if not task["build_commands"] or not task["artifact_stage_commands"] or any(token in command for command in commands for token in forbidden):
            raise QualificationError(f"{task['task_id']} reference commands 无效或包含网络动作")
        if task["oracle"].get("kind") not in {"compile_and_run", "command"}:
            raise QualificationError(f"{task['task_id']} oracle 无效")
    development_times = [_parse_time(task["commit_committed_at"]) for task in tasks if task["split"] != "evaluation"]
    evaluation_times = [_parse_time(task["commit_committed_at"]) for task in tasks if task["split"] == "evaluation"]
    if max(development_times) >= min(evaluation_times):
        raise QualificationError("evaluation exact commit 未实现严格时间后移")
    return pool


def validate_manifest(manifest: dict[str, Any], pool: dict[str, Any], *, check_schema: bool = True) -> dict[str, Any]:
    validate_source_pool(pool)
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("identity") != IDENTITY:
        raise QualificationError("manifest identity 无效")
    authorization = manifest.get("authorization", {})
    for key in (
        "provider_calls_authorized",
        "credential_read_authorized",
        "model_calls_authorized",
        "historical_evidence_write_authorized",
        "controller_implementation_authorized",
    ):
        if authorization.get(key) is not False:
            raise QualificationError(f"manifest 意外授权 {key}")
    if authorization.get("model_tokens_authorized") != 0 or authorization.get("new_identity_evidence_write_authorized") is not True:
        raise QualificationError("manifest 零 Provider 或新 identity 写入边界无效")
    if manifest["source_pool"]["canonical_sha256"] != canonical_sha256(pool):
        raise QualificationError("manifest source pool hash 漂移")
    historical = manifest["historical_coverage_audit"]
    for key in ("manifest", "report"):
        path = REPO_ROOT / historical[f"{key}_path"]
        if file_sha256(path) != historical[f"{key}_sha256"]:
            raise QualificationError(f"历史 {key} 只读输入漂移")
    if historical["expected_eligible_decisions"] != 409 or historical["counterfactual_outcomes_read"] is not False:
        raise QualificationError("历史覆盖审计边界漂移")
    if check_schema:
        schema = load_json(DEFAULT_SCHEMA)
        if schema != generate_schema(manifest):
            raise QualificationError("const Schema 漂移")
        jsonschema.validate(manifest, schema)
    return manifest


def load_contract() -> tuple[dict[str, Any], dict[str, Any]]:
    pool = validate_source_pool(load_json(DEFAULT_SOURCE_POOL))
    manifest = validate_manifest(load_json(DEFAULT_MANIFEST), pool)
    return manifest, pool


def generate_contract_files() -> None:
    pool = generate_source_pool()
    manifest = generate_manifest(pool)
    schema = generate_schema(manifest)
    jsonschema.Draft202012Validator.check_schema(schema)
    write_json(DEFAULT_SOURCE_POOL, pool)
    write_json(DEFAULT_MANIFEST, manifest)
    write_json(DEFAULT_SCHEMA, schema)


def _run_checked(argv: list[str], *, cwd: Path = REPO_ROOT, timeout: int = 120) -> str:
    result = subprocess.run(argv, cwd=cwd, check=False, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-MAX_LOG_BYTES:]
        raise QualificationError(f"命令失败 ({result.returncode}): {shlex.join(argv)}\n{detail}")
    return result.stdout.strip()


def require_zero_managed_resources() -> None:
    names = _run_checked(["docker", "ps", "-a", "--format", "{{.Names}}"])
    leftovers = sorted(name for name in names.splitlines() if name.startswith(MANAGED_PREFIX))
    if leftovers:
        raise QualificationError(f"存在 qualification orphan: {','.join(leftovers)}")


def current_image_id(manifest: dict[str, Any]) -> str:
    environment = manifest["environment"]
    dockerfile = REPO_ROOT / environment["dockerfile_path"]
    raw = _run_checked(
        [
            "docker",
            "image",
            "inspect",
            environment["image_tag"],
            "--format",
            f'{{{{.Id}}}}\t{{{{index .Config.Labels "{IMAGE_LABEL}"}}}}',
        ]
    )
    parts = raw.split("\t")
    if len(parts) != 2 or parts[0] != environment["expected_image_id"]:
        raise QualificationError("固定 qualification image ID 漂移")
    if parts[1] != file_sha256(dockerfile):
        raise QualificationError("固定 qualification image 未绑定当前 Dockerfile")
    return parts[0]


def preflight(manifest: dict[str, Any], pool: dict[str, Any]) -> dict[str, Any]:
    require_zero_managed_resources()
    image = current_image_id(manifest)
    historical = load_json(HISTORICAL_REPORT)
    observed = historical.get("observed_input", {})
    eligible = sum(int(split.get("row_count", 0)) for split in observed.values())
    if eligible != manifest["historical_coverage_audit"]["expected_eligible_decisions"]:
        raise QualificationError("历史 409 决策点摘要漂移")
    return {
        "ready": True,
        "identity": IDENTITY,
        "task_count": len(pool["tasks"]),
        "image_id": image,
        "historical_eligible_decisions": eligible,
        "provider_calls": 0,
        "credential_reads": 0,
        "model_tokens": 0,
        "managed_resources": 0,
    }


def _clone_exact(task: dict[str, Any], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    commands = (
        ["git", "init", "--quiet", str(destination)],
        [
            "git",
            "-C",
            str(destination),
            "remote",
            "add",
            "origin",
            task["repository_url"],
        ],
        [
            "git",
            "-C",
            str(destination),
            "-c",
            "credential.helper=",
            "fetch",
            "--quiet",
            "--depth",
            "1",
            "origin",
            task["commit_sha"],
        ],
        [
            "git",
            "-C",
            str(destination),
            "checkout",
            "--quiet",
            "--detach",
            "FETCH_HEAD",
        ],
    )
    for argv in commands:
        result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=600, env=env)
        if result.returncode != 0:
            raise QualificationError(f"{task['task_id']} exact clone 失败: {(result.stderr or result.stdout)[-MAX_LOG_BYTES:]}")
    if _run_checked(["git", "-C", str(destination), "rev-parse", "HEAD"]) != task["commit_sha"]:
        raise QualificationError(f"{task['task_id']} exact commit 漂移")


def _archive_sha256(source: Path) -> str:
    process = subprocess.Popen(
        ["git", "-C", str(source), "archive", "--format=tar", "HEAD"],
        stdout=subprocess.PIPE,
    )
    digest = hashlib.sha256()
    assert process.stdout is not None
    for chunk in iter(lambda: process.stdout.read(1024 * 1024), b""):
        digest.update(chunk)
    if process.wait(timeout=120) != 0:
        raise QualificationError("git archive 失败")
    return digest.hexdigest()


def _verify_source(task: dict[str, Any], source: Path) -> dict[str, Any]:
    archive_hash = _archive_sha256(source)
    license_path = source / task["license_path"]
    if archive_hash != task["source_snapshot_sha256"] or not license_path.is_file() or file_sha256(license_path) != task["license_sha256"]:
        raise QualificationError(f"{task['task_id']} source 或 license identity 漂移")
    tree = _run_checked(["git", "-C", str(source), "ls-tree", "-r", "HEAD"])
    submodules = {fields[3]: fields[2] for line in tree.splitlines() if len(fields := line.split(maxsplit=3)) == 4 and fields[0] == "160000"}
    if submodules != task["submodule_commits"]:
        raise QualificationError(f"{task['task_id']} submodule identity 漂移")
    return {
        "commit_sha": task["commit_sha"],
        "source_snapshot_sha256": archive_hash,
        "license_sha256": file_sha256(license_path),
        "submodule_commits": submodules,
    }


def _oracle_script(task: dict[str, Any], suffix: str) -> str:
    oracle = task["oracle"]
    if oracle["kind"] == "command":
        return shlex.join(oracle["argv"])
    extension = ".c" if oracle["language"] == "c11" else ".cc"
    source = f"/tmp/forge-typed-action-{suffix}{extension}"
    executable = f"/tmp/forge-typed-action-{suffix}"
    encoded = base64.b64encode(oracle["source"].encode()).decode()
    compile_argv = [source if item == "{source}" else executable if item == "{executable}" else item for item in oracle["compile_argv"]]
    run_argv = [executable if item == "{executable}" else item for item in oracle["run_argv"]]
    return f"printf %s {shlex.quote(encoded)} | base64 -d > {shlex.quote(source)}\n{shlex.join(compile_argv)}\n{shlex.join(run_argv)}"


def _dependency_command(task: dict[str, Any]) -> str:
    commands = {
        "cmake": "command -v cmake && command -v make && command -v cc && command -v c++",
        "make": "command -v make && command -v cc && command -v c++",
        "autotools": "command -v autoreconf && command -v automake && command -v libtoolize && command -v make && command -v cc",
    }
    return commands[task["selected_build_system"]]


def _diagnostic_command(task: dict[str, Any]) -> str:
    commands = {
        "cmake": "test -f CMakeLists.txt && cmake --version",
        "make": "test -f Makefile -o -f makefile && make --version",
        "autotools": "test -f configure.ac && autoreconf --version && make --version",
    }
    return commands[task["selected_build_system"]]


def _failure_command(task: dict[str, Any]) -> str:
    if task["selected_build_system"] == "cmake":
        return "cmake --build build --target forge_missing_target_389"
    return "make forge_missing_target_389"


def _commands_script(commands: list[str]) -> str:
    if not commands:
        raise QualificationError("候选动作缺少绑定命令")
    return "\n".join(commands)


def _bounded_tail(path: Path) -> str:
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(max(0, size - MAX_LOG_BYTES))
        return stream.read().decode("utf-8", errors="replace")


def _run_container(
    *,
    manifest: dict[str, Any],
    image: str,
    workspace: Path,
    artifacts: Path,
    script: str,
    log_path: Path,
    timeout: int | None = None,
) -> dict[str, Any]:
    name = f"{MANAGED_PREFIX}{uuid.uuid4().hex[:12]}"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        "docker",
        "run",
        "--name",
        name,
        "--label",
        "forge.typed-action.qualification=true",
        "--network",
        "none",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env",
        "HOME=/tmp",
        "--cpus",
        str(manifest["environment"]["parallel_jobs"]),
        "--volume",
        f"{workspace.resolve()}:/workspace/repo",
        "--volume",
        f"{artifacts.resolve()}:/artifacts",
        "--workdir",
        "/workspace/repo",
        image,
        "bash",
        "-lc",
        "set -euo pipefail\n" + script,
    ]
    started = time.perf_counter()
    timed_out = False
    exit_code: int | None = None
    try:
        with log_path.open("wb") as stream:
            try:
                result = subprocess.run(
                    argv,
                    check=False,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=timeout or manifest["environment"]["per_action_timeout_seconds"],
                )
                exit_code = result.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "log_sha256": file_sha256(log_path),
        "log_tail": _bounded_tail(log_path),
    }


def _artifact_evidence(task: dict[str, Any], artifacts: Path) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    target = task["target"]
    for relative, expected_type in zip(target["required_artifacts"], target["artifact_types"], strict=True):
        path = artifacts / relative
        if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
            raise QualificationError(f"{task['task_id']} 缺少 required artifact: {relative}")
        file_type = _run_checked(["file", "-b", str(path)])
        if expected_type == "static_library" and not _run_checked(["ar", "t", str(path)]):
            raise QualificationError(f"{task['task_id']} 空静态库: {relative}")
        if expected_type == "executable" and "executable" not in file_type.lower():
            raise QualificationError(f"{task['task_id']} 非 executable: {relative}")
        evidence.append(
            {
                "path": relative,
                "type": expected_type,
                "size_bytes": path.stat().st_size,
                "sha256": file_sha256(path),
                "file_type": file_type,
            }
        )
    return evidence


def _copy_tree(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        destination.mkdir(parents=True)


def _facts(
    *,
    configured: bool | None,
    built: bool,
    staged: bool,
    dependency_ready: bool = False,
) -> dict[str, bool | None]:
    return {
        "source_available": True,
        "dependency_ready": dependency_ready,
        "configured": configured,
        "build_succeeded": built,
        "artifacts_staged": staged,
        "functional_oracle_passed": False,
        "strict_verifier_passed": False,
    }


def _evidence_rank(facts: dict[str, Any]) -> int:
    ordered = (
        "dependency_ready",
        "configured",
        "build_succeeded",
        "artifacts_staged",
        "functional_oracle_passed",
        "strict_verifier_passed",
    )
    return sum(1 for name in ordered if facts.get(name) is True)


def _candidate_families(task: dict[str, Any], state_kind: str) -> list[str]:
    has_configure = bool(task["configure_commands"])
    if state_kind == "source_ready":
        return [
            "dependency",
            "configure" if has_configure else "build",
            "diagnostic_probe",
        ]
    if state_kind == "configured_or_ready":
        return ["build", "smoke", "diagnostic_probe"]
    if state_kind == "build_failed":
        return ["configure", "build", "diagnostic_probe"] if has_configure else ["build", "diagnostic_probe", "escalate_agent"]
    if state_kind == "built":
        return ["smoke", "artifact_stage", "escalate_agent"]
    if state_kind == "staged":
        return ["smoke", "submit", "artifact_stage"]
    raise QualificationError(f"未知 state kind: {state_kind}")


def _action_command(task: dict[str, Any], family: str, suffix: str) -> tuple[str, str | None]:
    if family == "dependency":
        return "docker_command", _dependency_command(task)
    if family == "configure":
        return "docker_command", _commands_script(task["configure_commands"])
    if family == "build":
        return "docker_command", _commands_script(task["build_commands"])
    if family == "diagnostic_probe":
        return "docker_command", _diagnostic_command(task)
    if family == "smoke":
        return "docker_command", _oracle_script(task, suffix)
    if family == "artifact_stage":
        return "docker_command", _commands_script(task["artifact_stage_commands"])
    if family == "submit":
        return "strict_submit_verifier", None
    if family == "escalate_agent":
        return "agent_handoff", None
    raise QualificationError(f"未知 action family: {family}")


def _action_contract(task: dict[str, Any], state_id: str, family: str) -> dict[str, Any]:
    executor, command = _action_command(task, family, state_id.replace(":", "-"))
    expected = {
        "dependency": ["dependency_ready"],
        "configure": ["configured"],
        "build": ["build_succeeded"],
        "diagnostic_probe": ["bounded_diagnostic"],
        "smoke": ["functional_oracle_passed"],
        "artifact_stage": ["artifacts_staged"],
        "submit": ["strict_verifier_passed"],
        "escalate_agent": ["full_agent_handoff"],
    }[family]
    risk = "high" if family == "submit" else "medium" if family in {"dependency", "configure", "build", "artifact_stage"} else "low"
    return {
        "action_id": f"{state_id}:{family}",
        "action_family": family,
        "executor": executor,
        "bound_command": command,
        "preconditions_checked_by_runner": True,
        "expected_evidence": expected,
        "risk_level": risk,
    }


def _extract_clean_source(workspace: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    archive = subprocess.Popen(
        ["git", "-C", str(workspace), "archive", "--format=tar", "HEAD"],
        stdout=subprocess.PIPE,
    )
    assert archive.stdout is not None
    extract = subprocess.run(
        ["tar", "-xf", "-", "-C", str(destination)],
        stdin=archive.stdout,
        check=False,
        capture_output=True,
    )
    archive.stdout.close()
    archive_code = archive.wait(timeout=120)
    if archive_code != 0 or extract.returncode != 0:
        raise QualificationError("strict submit clean source 提取失败")


def _strict_submit(
    *,
    manifest: dict[str, Any],
    image: str,
    task: dict[str, Any],
    workspace: Path,
    artifacts: Path,
    root: Path,
    log_path: Path,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        original = _artifact_evidence(task, artifacts)
    except QualificationError as exc:
        log_path.write_text(str(exc) + "\n", encoding="utf-8")
        return {
            "exit_code": 1,
            "timed_out": False,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "log_sha256": file_sha256(log_path),
            "log_tail": str(exc),
            "strict_checks": {
                "candidate": False,
                "functional": False,
                "provenance": False,
                "clean_replay": False,
            },
        }
    provenance = _run_checked(["git", "-C", str(workspace), "rev-parse", "HEAD"]) == task["commit_sha"]
    replay_workspace = root / "strict-replay-workspace"
    replay_artifacts = root / "strict-replay-artifacts"
    _extract_clean_source(workspace, replay_workspace)
    replay_artifacts.mkdir()
    script = _commands_script(
        [
            *task["configure_commands"],
            *task["build_commands"],
            *task["artifact_stage_commands"],
            _oracle_script(task, "strict-replay"),
        ]
    )
    execution = _run_container(
        manifest=manifest,
        image=image,
        workspace=replay_workspace,
        artifacts=replay_artifacts,
        script=script,
        log_path=log_path,
    )
    functional = execution["exit_code"] == 0 and not execution["timed_out"]
    replay_evidence: list[dict[str, Any]] = []
    if functional:
        try:
            replay_evidence = _artifact_evidence(task, replay_artifacts)
        except QualificationError:
            functional = False
    clean_replay = functional and [item["path"] for item in original] == [item["path"] for item in replay_evidence]
    if clean_replay and task["target"]["bitwise_required"]:
        clean_replay = [item["sha256"] for item in original] == [item["sha256"] for item in replay_evidence]
    passed = provenance and functional and clean_replay
    execution["exit_code"] = 0 if passed else 1
    execution["duration_seconds"] = round(time.perf_counter() - started, 3)
    execution["strict_checks"] = {
        "candidate": True,
        "functional": functional,
        "provenance": provenance,
        "clean_replay": clean_replay,
    }
    return execution


def _execute_candidate(
    *,
    manifest: dict[str, Any],
    image: str,
    task: dict[str, Any],
    state: dict[str, Any],
    action: dict[str, Any],
    workspace: Path,
    artifacts: Path,
    root: Path,
) -> dict[str, Any]:
    family = action["action_family"]
    log_path = root / "action.log"
    if action["executor"] == "agent_handoff":
        log_path.write_text("escalate_agent\n", encoding="utf-8")
        execution: dict[str, Any] = {
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 0.0,
            "log_sha256": file_sha256(log_path),
            "log_tail": "escalate_agent",
        }
    elif action["executor"] == "strict_submit_verifier":
        execution = _strict_submit(
            manifest=manifest,
            image=image,
            task=task,
            workspace=workspace,
            artifacts=artifacts,
            root=root,
            log_path=log_path,
        )
    else:
        execution = _run_container(
            manifest=manifest,
            image=image,
            workspace=workspace,
            artifacts=artifacts,
            script=action["bound_command"],
            log_path=log_path,
        )
    success = execution["exit_code"] == 0 and not execution["timed_out"]
    if family == "submit":
        strict_checks = execution.get("strict_checks")
        success = success and isinstance(strict_checks, dict) and all(strict_checks.get(name) is True for name in ("candidate", "functional", "provenance", "clean_replay"))
        if not success:
            execution["exit_code"] = 1
    after = dict(state["phase_facts"])
    if success and family == "dependency":
        after["dependency_ready"] = True
    elif success and family == "configure":
        after["configured"] = True
    elif success and family == "build":
        after["build_succeeded"] = True
    elif success and family == "smoke":
        after["functional_oracle_passed"] = True
    elif success and family == "artifact_stage":
        try:
            _artifact_evidence(task, artifacts)
            after["artifacts_staged"] = True
        except QualificationError:
            success = False
            execution["exit_code"] = 1
    elif success and family == "submit":
        after["functional_oracle_passed"] = True
        after["strict_verifier_passed"] = True
    direct_safe = success and family != "escalate_agent"
    progressed = _evidence_rank(after) > _evidence_rank(state["phase_facts"])
    signature = {
        "action_family": family,
        "exit_class": "timeout" if execution["timed_out"] else "success" if execution["exit_code"] == 0 else "failure",
        "direct_execution_safe": direct_safe,
        "progressed": progressed,
        "eligible_next_action": direct_safe and progressed,
        "phase_facts_after": after,
    }
    return {
        "state_id": state["state_id"],
        "action_id": action["action_id"],
        "action_family": family,
        "exit_code": execution["exit_code"],
        "timed_out": execution["timed_out"],
        "duration_seconds": execution["duration_seconds"],
        "log_sha256": execution["log_sha256"],
        "log_tail": execution["log_tail"],
        "direct_execution_safe": direct_safe,
        "route_acceptable": direct_safe or family == "escalate_agent",
        "progressed": progressed,
        "eligible_next_action": direct_safe and progressed,
        "phase_facts_after": after,
        "strict_checks": execution.get("strict_checks"),
        "replay_signature": signature,
    }


def _pipeline_step(
    *,
    manifest: dict[str, Any],
    image: str,
    workspace: Path,
    artifacts: Path,
    script: str,
    log_path: Path,
    should_succeed: bool,
) -> dict[str, Any]:
    result = _run_container(
        manifest=manifest,
        image=image,
        workspace=workspace,
        artifacts=artifacts,
        script=script,
        log_path=log_path,
    )
    succeeded = result["exit_code"] == 0 and not result["timed_out"]
    if succeeded != should_succeed:
        expectation = "成功" if should_succeed else "受控失败"
        raise QualificationError(f"pipeline step 未按预期{expectation}: {result['log_tail']}")
    return result


def _state_record(
    *,
    task: dict[str, Any],
    state_kind: str,
    facts: dict[str, Any],
    last_action: dict[str, Any] | None,
) -> dict[str, Any]:
    state_id = f"{task['task_id']}:{state_kind}"
    actions = [_action_contract(task, state_id, family) for family in _candidate_families(task, state_kind)]
    return {
        "state_id": state_id,
        "project_id": task["task_id"],
        "project_family": task["project_family"],
        "split": task["split"],
        "build_system": task["selected_build_system"],
        "state_kind": state_kind,
        "phase_facts": facts,
        "last_action": last_action,
        "log_summary": None if last_action is None else last_action["log_tail"],
        "artifact_status": "staged" if facts["artifacts_staged"] else "not_staged",
        "verifier_status": "passed" if facts["strict_verifier_passed"] else "not_run",
        "remaining_budget": {"actions": 12, "wall_clock_seconds": 900},
        "candidate_actions": actions,
    }


def _evaluate_state(
    *,
    manifest: dict[str, Any],
    image: str,
    task: dict[str, Any],
    state: dict[str, Any],
    workspace: Path,
    artifacts: Path,
    replicate: int,
    root: Path,
) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for action in state["candidate_actions"]:
        with tempfile.TemporaryDirectory(prefix=f"candidate-{task['task_id']}-", dir=root) as temporary:
            candidate_root = Path(temporary)
            candidate_workspace = candidate_root / "workspace"
            candidate_artifacts = candidate_root / "artifacts"
            _copy_tree(workspace, candidate_workspace)
            _copy_tree(artifacts, candidate_artifacts)
            outcome = _execute_candidate(
                manifest=manifest,
                image=image,
                task=task,
                state=state,
                action=action,
                workspace=candidate_workspace,
                artifacts=candidate_artifacts,
                root=candidate_root,
            )
            outcome["replicate"] = replicate
            outcomes.append(outcome)
    return outcomes


def _last_action(family: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_family": family,
        "succeeded": result["exit_code"] == 0 and not result["timed_out"],
        "exit_code": result["exit_code"],
        "timed_out": result["timed_out"],
        "log_sha256": result["log_sha256"],
        "log_tail": result["log_tail"],
    }


def _run_project_replicate(
    *,
    manifest: dict[str, Any],
    image: str,
    task: dict[str, Any],
    replicate: int,
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    project_root = root / f"{task['task_id']}-r{replicate}"
    workspace = project_root / "workspace"
    artifacts = project_root / "artifacts"
    project_root.mkdir(parents=True)
    _clone_exact(task, workspace)
    source_identity = _verify_source(task, workspace)
    artifacts.mkdir()
    state_records: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []

    configured_fact: bool | None = False if task["configure_commands"] else None
    source_state = _state_record(
        task=task,
        state_kind="source_ready",
        facts=_facts(configured=configured_fact, built=False, staged=False),
        last_action=None,
    )
    state_records.append(source_state)
    outcomes.extend(
        _evaluate_state(
            manifest=manifest,
            image=image,
            task=task,
            state=source_state,
            workspace=workspace,
            artifacts=artifacts,
            replicate=replicate,
            root=project_root,
        )
    )

    dependency = _pipeline_step(
        manifest=manifest,
        image=image,
        workspace=workspace,
        artifacts=artifacts,
        script=_dependency_command(task),
        log_path=project_root / "pipeline-dependency.log",
        should_succeed=True,
    )
    last = _last_action("dependency", dependency)
    if task["configure_commands"]:
        configured = _pipeline_step(
            manifest=manifest,
            image=image,
            workspace=workspace,
            artifacts=artifacts,
            script=_commands_script(task["configure_commands"]),
            log_path=project_root / "pipeline-configure.log",
            should_succeed=True,
        )
        last = _last_action("configure", configured)
        configured_fact = True
    ready_state = _state_record(
        task=task,
        state_kind="configured_or_ready",
        facts=_facts(configured=configured_fact, built=False, staged=False, dependency_ready=True),
        last_action=last,
    )
    state_records.append(ready_state)
    outcomes.extend(
        _evaluate_state(
            manifest=manifest,
            image=image,
            task=task,
            state=ready_state,
            workspace=workspace,
            artifacts=artifacts,
            replicate=replicate,
            root=project_root,
        )
    )

    failure = _pipeline_step(
        manifest=manifest,
        image=image,
        workspace=workspace,
        artifacts=artifacts,
        script=_failure_command(task),
        log_path=project_root / "pipeline-controlled-failure.log",
        should_succeed=False,
    )
    failed_state = _state_record(
        task=task,
        state_kind="build_failed",
        facts=_facts(configured=configured_fact, built=False, staged=False, dependency_ready=True),
        last_action=_last_action("build", failure),
    )
    state_records.append(failed_state)
    outcomes.extend(
        _evaluate_state(
            manifest=manifest,
            image=image,
            task=task,
            state=failed_state,
            workspace=workspace,
            artifacts=artifacts,
            replicate=replicate,
            root=project_root,
        )
    )

    build = _pipeline_step(
        manifest=manifest,
        image=image,
        workspace=workspace,
        artifacts=artifacts,
        script=_commands_script(task["build_commands"]),
        log_path=project_root / "pipeline-build.log",
        should_succeed=True,
    )
    built_state = _state_record(
        task=task,
        state_kind="built",
        facts=_facts(configured=configured_fact, built=True, staged=False, dependency_ready=True),
        last_action=_last_action("build", build),
    )
    state_records.append(built_state)
    outcomes.extend(
        _evaluate_state(
            manifest=manifest,
            image=image,
            task=task,
            state=built_state,
            workspace=workspace,
            artifacts=artifacts,
            replicate=replicate,
            root=project_root,
        )
    )

    stage = _pipeline_step(
        manifest=manifest,
        image=image,
        workspace=workspace,
        artifacts=artifacts,
        script=_commands_script(task["artifact_stage_commands"]),
        log_path=project_root / "pipeline-artifact-stage.log",
        should_succeed=True,
    )
    artifact_evidence = _artifact_evidence(task, artifacts)
    staged_state = _state_record(
        task=task,
        state_kind="staged",
        facts=_facts(configured=configured_fact, built=True, staged=True, dependency_ready=True),
        last_action=_last_action("artifact_stage", stage),
    )
    state_records.append(staged_state)
    outcomes.extend(
        _evaluate_state(
            manifest=manifest,
            image=image,
            task=task,
            state=staged_state,
            workspace=workspace,
            artifacts=artifacts,
            replicate=replicate,
            root=project_root,
        )
    )
    smoke = _pipeline_step(
        manifest=manifest,
        image=image,
        workspace=workspace,
        artifacts=artifacts,
        script=_oracle_script(task, f"reference-{replicate}"),
        log_path=project_root / "pipeline-reference-smoke.log",
        should_succeed=True,
    )
    closure = {
        "task_id": task["task_id"],
        "replicate": replicate,
        "source_identity": source_identity,
        "reference_smoke_passed": True,
        "reference_smoke_log_sha256": smoke["log_sha256"],
        "artifacts": artifact_evidence,
    }
    return state_records, outcomes, closure


def _historical_catalog_coverage(states: list[dict[str, Any]]) -> dict[str, Any]:
    catalog_cells = {(state["build_system"], action["action_family"]) for state in states for action in state["candidate_actions"]}
    role_mapping = {
        "dependency": "dependency",
        "configure": "configure",
        "build": "build",
        "diagnostic": "diagnostic_probe",
        "smoke": "smoke",
        "artifact_stage": "artifact_stage",
    }
    historical_manifest = load_json(HISTORICAL_MANIFEST)
    total = 0
    covered = 0
    roles = Counter()
    covered_roles = Counter()
    for item in historical_manifest["inputs"]:
        session_path = SESSIONS_ROOT / item["session_path"]
        if not session_path.is_file() or file_sha256(session_path) != item["session_sha256"]:
            raise QualificationError(f"历史只读 session 缺失或漂移: {item['session_path']}")
        session = load_json(session_path)
        for command in session.get("commands", []):
            role = command.get("role")
            if role not in role_mapping:
                continue
            total += 1
            roles[role] += 1
            if (item["build_system"], role_mapping[role]) in catalog_cells:
                covered += 1
                covered_roles[role] += 1
    if total != 409:
        raise QualificationError(f"历史 eligible decision 数量漂移: {total}")
    return {
        "eligible_decisions": total,
        "covered_decisions": covered,
        "coverage": covered / total,
        "roles": dict(sorted(roles.items())),
        "covered_roles": dict(sorted(covered_roles.items())),
        "raw_commands_used_as_labels": False,
        "counterfactual_outcomes_read": False,
        "historical_evidence_modified": False,
    }


def _qualification_metrics(
    *,
    manifest: dict[str, Any],
    pool: dict[str, Any],
    states: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    closures: list[dict[str, Any]],
) -> dict[str, Any]:
    thresholds = manifest["qualification_thresholds"]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for outcome in outcomes:
        grouped[(outcome["state_id"], outcome["action_family"])].append(outcome)
    replay_pairs = len(grouped)
    consistent_pairs = sum(1 for values in grouped.values() if len(values) == manifest["environment"]["replicates"] and canonical_sha256(values[0]["replay_signature"]) == canonical_sha256(values[1]["replay_signature"]))
    consistency = consistent_pairs / replay_pairs if replay_pairs else 0.0
    action_state_coverage: Counter[str] = Counter()
    for state in states:
        for action in state["candidate_actions"]:
            action_state_coverage[action["action_family"]] += 1
    build_system_projects = Counter(task["selected_build_system"] for task in pool["tasks"])
    split_projects = Counter(task["split"] for task in pool["tasks"])
    build_system_states = Counter(state["build_system"] for state in states)
    reference_closure_count = sum(1 for closure in closures if closure["reference_smoke_passed"])
    expected_outcomes = len(states) * manifest["benchmark_design"]["candidate_actions_per_state"] * manifest["environment"]["replicates"]
    complete_systems = all(
        build_system_projects[build_system] == thresholds["projects_per_build_system"] and build_system_states[build_system] == thresholds["projects_per_build_system"] * thresholds["states_per_project"] for build_system in BUILD_SYSTEMS
    )
    minimum_action_coverage = min(action_state_coverage.values()) if action_state_coverage else 0
    return {
        "project_count": len(pool["tasks"]),
        "projects_by_split": dict(sorted(split_projects.items())),
        "projects_by_build_system": dict(sorted(build_system_projects.items())),
        "state_count": len(states),
        "states_by_build_system": dict(sorted(build_system_states.items())),
        "candidate_outcome_count": len(outcomes),
        "expected_candidate_outcome_count": expected_outcomes,
        "reference_closure_count": reference_closure_count,
        "expected_reference_closure_count": len(pool["tasks"]) * manifest["environment"]["replicates"],
        "action_family_state_coverage": dict(sorted(action_state_coverage.items())),
        "minimum_action_family_state_coverage": minimum_action_coverage,
        "replay_pair_count": replay_pairs,
        "consistent_replay_pair_count": consistent_pairs,
        "replay_consistency": consistency,
        "all_build_systems_complete": complete_systems,
        "all_candidates_bounded": all(outcome["exit_code"] is not None or outcome["timed_out"] for outcome in outcomes),
    }


def _adjudicate(manifest: dict[str, Any], metrics: dict[str, Any], historical: dict[str, Any]) -> dict[str, Any]:
    thresholds = manifest["qualification_thresholds"]
    checks = {
        "project_count": metrics["project_count"] == thresholds["project_count"],
        "split_counts": metrics["projects_by_split"]
        == {
            "calibration": thresholds["calibration_projects"],
            "design": thresholds["design_projects"],
            "evaluation": thresholds["evaluation_projects"],
        },
        "state_count": metrics["state_count"] == thresholds["project_count"] * thresholds["states_per_project"],
        "candidate_execution_count": metrics["candidate_outcome_count"] == metrics["expected_candidate_outcome_count"],
        "reference_closure": metrics["reference_closure_count"] == metrics["expected_reference_closure_count"],
        "action_family_coverage": metrics["minimum_action_family_state_coverage"] >= thresholds["minimum_states_per_action_family"],
        "replay_consistency": metrics["replay_consistency"] >= thresholds["minimum_replay_consistency"],
        "historical_catalog_coverage": historical["coverage"] >= thresholds["minimum_historical_catalog_coverage"],
        "all_build_systems_complete": metrics["all_build_systems_complete"],
        "all_candidates_bounded": metrics["all_candidates_bounded"],
    }
    passed = all(checks.values())
    return {
        "passed": passed,
        "checks": checks,
        "decision": manifest["decision_rule"]["pass" if passed else "fail"],
        "thresholds_adjusted_after_results": False,
    }


def run_qualification(
    manifest: dict[str, Any],
    pool: dict[str, Any],
    *,
    output_json: Path = DEFAULT_JSON_REPORT,
    output_markdown: Path = DEFAULT_MARKDOWN_REPORT,
    work_root: Path | None = None,
) -> dict[str, Any]:
    if output_json.exists() or output_markdown.exists():
        raise QualificationError("资格报告已存在，禁止覆盖")
    readiness = preflight(manifest, pool)
    image = readiness["image_id"]
    owner = tempfile.TemporaryDirectory(prefix="forge-typed-action-q-") if work_root is None else None
    root = Path(owner.name) if owner is not None else work_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    states: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    closures: list[dict[str, Any]] = []
    try:
        for task in pool["tasks"]:
            first_states: list[dict[str, Any]] | None = None
            for replicate in range(1, manifest["environment"]["replicates"] + 1):
                print(f"[{task['task_id']}] replicate {replicate}/2", flush=True)
                replicate_states, replicate_outcomes, closure = _run_project_replicate(
                    manifest=manifest,
                    image=image,
                    task=task,
                    replicate=replicate,
                    root=root,
                )
                semantic_states = [
                    {
                        "state_id": state["state_id"],
                        "project_id": state["project_id"],
                        "build_system": state["build_system"],
                        "state_kind": state["state_kind"],
                        "phase_facts": state["phase_facts"],
                        "candidate_actions": state["candidate_actions"],
                    }
                    for state in replicate_states
                ]
                if first_states is None:
                    first_states = semantic_states
                    states.extend(replicate_states)
                elif canonical_sha256(first_states) != canonical_sha256(semantic_states):
                    raise QualificationError(f"{task['task_id']} state contract 在 replicate 间漂移")
                outcomes.extend(replicate_outcomes)
                closures.append(closure)
                require_zero_managed_resources()
    finally:
        if owner is not None:
            owner.cleanup()
    historical = _historical_catalog_coverage(states)
    metrics = _qualification_metrics(
        manifest=manifest,
        pool=pool,
        states=states,
        outcomes=outcomes,
        closures=closures,
    )
    adjudication = _adjudicate(manifest, metrics, historical)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "document_type": "forge_typed_action_benchmark_qualification_report",
        "identity": IDENTITY,
        "issue_url": ISSUE_URL,
        "completed_at": datetime.now(UTC).isoformat(),
        "status": "passed" if adjudication["passed"] else "failed",
        "work_type": "zero_provider_benchmark_qualification",
        "manifest_canonical_sha256": canonical_sha256(manifest),
        "source_pool_canonical_sha256": canonical_sha256(pool),
        "image_id": image,
        "provider_calls": 0,
        "credential_reads": 0,
        "model_calls": 0,
        "model_tokens": 0,
        "historical_evidence_modified": False,
        "controller_implemented": False,
        "states": states,
        "candidate_outcomes": outcomes,
        "reference_closures": closures,
        "historical_catalog_coverage": historical,
        "metrics": metrics,
        "adjudication": adjudication,
        "claim_boundary": {
            "benchmark_executability_only": True,
            "jev_effect_estimated": False,
            "controller_effect_estimated": False,
            "old_agent_actions_used_as_truth": False,
            "strict_submit_includes": [
                "candidate",
                "functional",
                "provenance",
                "clean_replay",
            ],
        },
    }
    validate_report(report, manifest, pool)
    write_once(
        output_json,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    write_once(output_markdown, render_markdown(report))
    require_zero_managed_resources()
    return report


def validate_report(report: dict[str, Any], manifest: dict[str, Any], pool: dict[str, Any]) -> dict[str, Any]:
    if report.get("schema_version") != REPORT_SCHEMA_VERSION or report.get("identity") != IDENTITY:
        raise QualificationError("report identity 无效")
    if report.get("manifest_canonical_sha256") != canonical_sha256(manifest) or report.get("source_pool_canonical_sha256") != canonical_sha256(pool):
        raise QualificationError("report 输入 identity 漂移")
    for key in ("provider_calls", "credential_reads", "model_calls", "model_tokens"):
        if report.get(key) != 0:
            raise QualificationError(f"report {key} 必须为 0")
    if report.get("historical_evidence_modified") is not False or report.get("controller_implemented") is not False:
        raise QualificationError("report 越出阶段 A 边界")
    states = report.get("states")
    outcomes = report.get("candidate_outcomes")
    closures = report.get("reference_closures")
    if not isinstance(states, list) or not isinstance(outcomes, list) or not isinstance(closures, list):
        raise QualificationError("report 状态或 outcome matrix 缺失")
    if len(states) != 120 or any(len(state.get("candidate_actions", [])) != 3 for state in states):
        raise QualificationError("report 必须包含 120 个状态且每状态 3 个候选动作")
    if len({state["state_id"] for state in states}) != 120:
        raise QualificationError("report state_id 重复")
    expected_action_ids = {action["action_id"] for state in states for action in state["candidate_actions"]}
    if {outcome.get("action_id") for outcome in outcomes} != expected_action_ids or len(outcomes) != len(expected_action_ids) * 2:
        raise QualificationError("report outcome matrix 不完整")
    groups: Counter[tuple[str, str]] = Counter((outcome["state_id"], outcome["action_family"]) for outcome in outcomes)
    if not groups or set(groups.values()) != {2}:
        raise QualificationError("report 每个 state/action 必须有两次 replay")
    for outcome in outcomes:
        if outcome["action_family"] == "submit" and outcome["direct_execution_safe"]:
            checks = outcome.get("strict_checks")
            if not isinstance(checks, dict) or not all(checks.get(name) is True for name in ("candidate", "functional", "provenance", "clean_replay")):
                raise QualificationError("安全 submit 未闭合四层严格检查")
    if len(closures) != 48 or any(closure.get("reference_smoke_passed") is not True for closure in closures):
        raise QualificationError("report reference closure 不完整")
    metrics = _qualification_metrics(
        manifest=manifest,
        pool=pool,
        states=states,
        outcomes=outcomes,
        closures=closures,
    )
    if report.get("metrics") != metrics:
        raise QualificationError("report metrics 无法从 outcome matrix 重建")
    historical = report.get("historical_catalog_coverage")
    if not isinstance(historical, dict) or historical.get("eligible_decisions") != 409:
        raise QualificationError("report 历史覆盖审计无效")
    adjudication = _adjudicate(manifest, metrics, historical)
    if report.get("adjudication") != adjudication:
        raise QualificationError("report adjudication 漂移")
    expected_status = "passed" if adjudication["passed"] else "failed"
    if report.get("status") != expected_status:
        raise QualificationError("report status 与 adjudication 不一致")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    historical = report["historical_catalog_coverage"]
    adjudication = report["adjudication"]
    check_order = (
        "project_count",
        "split_counts",
        "state_count",
        "candidate_execution_count",
        "reference_closure",
        "action_family_coverage",
        "replay_consistency",
        "historical_catalog_coverage",
        "all_build_systems_complete",
        "all_candidates_bounded",
    )
    checks = "\n".join(f"| `{name}` | {'通过' if adjudication['checks'][name] else '失败'} |" for name in check_order)
    actions = "\n".join(f"| `{family}` | {count} |" for family, count in metrics["action_family_state_coverage"].items())
    systems = "\n".join(f"| {system} | {metrics['projects_by_build_system'][system]} | {metrics['states_by_build_system'][system]} |" for system in sorted(metrics["projects_by_build_system"]))
    qualification_summary = (
        f"共资格审计 {metrics['project_count']} 个项目、{metrics['state_count']} 个状态、{metrics['candidate_outcome_count']} 次隔离候选执行。"
        f"两次 replay 的 categorical outcome 一致率为 `{metrics['replay_consistency']:.4f}`"
        f"（{metrics['consistent_replay_pair_count']}/{metrics['replay_pair_count']}）。"
        f"旧 409 个决策点的动作目录覆盖率为 `{historical['coverage']:.4f}`"
        f"（{historical['covered_decisions']}/{historical['eligible_decisions']}）。"
    )
    interpretation_boundary = (
        "本报告只证明跨 CMake、Make、Autotools 的闭集候选动作 benchmark 在固定镜像上是否可执行和可重复。"
        "动作标签来自隔离执行后的真实证据；旧 Agent 动作未作为正确标签，旧 409 点只用于目录覆盖率。"
        "`submit` 只有在 candidate、functional、provenance 和 clean replay 四项全部闭合时才标记为可直接执行。"
    )
    return f"""# Jev 类型化动作 benchmark 阶段 A 资格报告

- identity：`{report["identity"]}`
- Issue：{report["issue_url"]}
- 完成时间：`{report["completed_at"]}`
- 状态：`{report["status"]}`
- 决定：`{adjudication["decision"]}`

## 资格结果

| 门槛 | 结果 |
|---|---|
{checks}

{qualification_summary}

## 构建系统覆盖

| 构建系统 | 项目 | 状态 |
|---|---:|---:|
{systems}

## 动作覆盖

| 动作族 | 独立状态数 |
|---|---:|
{actions}

## 解释边界

{interpretation_boundary}

本阶段调用 Provider `0` 次，读取 credential `0` 次，模型调用 `0` 次，模型 token `0`；没有实现 Jev controller，也没有修改历史 evidence。因此本报告不能说明 Jev 判断准确率、校准质量、成本收益或端到端成功率。
"""


def rule_gate_action(state: dict[str, Any]) -> str:
    """只使用确定性阶段事实的冻结 RuleGate。"""
    facts = state["phase_facts"]
    families = {action["action_family"] for action in state["candidate_actions"]}
    if facts["artifacts_staged"]:
        return "submit"
    if facts["build_succeeded"]:
        return "artifact_stage"
    if facts["configured"] is False and "configure" in families:
        return "configure"
    return "build"


def generate_rule_gate_audit(qualification_report: dict[str, Any]) -> dict[str, Any]:
    outcomes_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for outcome in qualification_report["candidate_outcomes"]:
        outcomes_by_key[(outcome["state_id"], outcome["action_family"])].append(outcome)
    rows: list[dict[str, Any]] = []
    eligible_counts: Counter[int] = Counter()
    for state in qualification_report["states"]:
        selected = rule_gate_action(state)
        selected_outcomes = outcomes_by_key[(state["state_id"], selected)]
        if len(selected_outcomes) != 2 or canonical_sha256(selected_outcomes[0]["replay_signature"]) != canonical_sha256(selected_outcomes[1]["replay_signature"]):
            raise QualificationError(f"RuleGate 所选 outcome 缺少一致 replay: {state['state_id']}")
        eligible_count = sum(outcomes_by_key[(state["state_id"], action["action_family"])][0]["eligible_next_action"] for action in state["candidate_actions"])
        eligible_counts[eligible_count] += 1
        outcome = selected_outcomes[0]
        rows.append(
            {
                "state_id": state["state_id"],
                "split": state["split"],
                "build_system": state["build_system"],
                "state_kind": state["state_kind"],
                "selected_action_family": selected,
                "direct_execution_safe": outcome["direct_execution_safe"],
                "eligible_next_action": outcome["eligible_next_action"],
                "semantic_log_used": False,
            }
        )

    def summary(selected_rows: list[dict[str, Any]]) -> dict[str, Any]:
        count = len(selected_rows)
        safe = sum(row["direct_execution_safe"] for row in selected_rows)
        eligible = sum(row["eligible_next_action"] for row in selected_rows)
        return {
            "state_count": count,
            "safe_count": safe,
            "eligible_count": eligible,
            "top1_safe_rate": safe / count,
            "direct_execution_coverage": eligible / count,
            "wrong_direct_action_rate": (count - safe) / count,
        }

    overall = summary(rows)
    by_build_system = {build_system: summary([row for row in rows if row["build_system"] == build_system]) for build_system in BUILD_SYSTEMS}
    by_split = {split: summary([row for row in rows if row["split"] == split]) for split in SPLITS}
    required_uplift = 0.10
    maximum_possible_uplift = 1.0 - overall["direct_execution_coverage"]
    entry_identifiable = maximum_possible_uplift >= required_uplift
    return {
        "schema_version": "forge-typed-action-rule-gate-audit-1.0.0",
        "document_type": "forge_typed_action_rule_gate_audit",
        "identity": "cpp-typed-action-benchmark-rule-gate-audit-v1",
        "issue_url": ISSUE_URL,
        "analysis_kind": "zero_provider_phase_b_entry_identifiability",
        "source_qualification_report_path": DEFAULT_JSON_REPORT.relative_to(REPO_ROOT).as_posix(),
        "source_qualification_report_sha256": file_sha256(DEFAULT_JSON_REPORT),
        "rule_gate_inputs": ["phase_facts", "candidate_action_families"],
        "semantic_log_used": False,
        "provider_calls": 0,
        "credential_reads": 0,
        "model_calls": 0,
        "model_tokens": 0,
        "overall": overall,
        "by_build_system": by_build_system,
        "by_split": by_split,
        "eligible_action_multiplicity": {str(count): states for count, states in sorted(eligible_counts.items())},
        "phase_b_entry_gate": {
            "required_rule_gate_coverage_uplift": required_uplift,
            "maximum_possible_coverage_uplift": maximum_possible_uplift,
            "jev_entry_identifiable": entry_identifiable,
        },
        "decision": ("proceed_to_jev_offline_qualification" if entry_identifiable else "stop_jev_provider_qualification_and_redesign_benchmark"),
        "interpretation": {
            "qualification_executability_passed": True,
            "semantic_routing_question_identifiable": entry_identifiable,
            "jev_model_effect_estimated": False,
            "rule_gate_saturation_is_jev_failure": False,
            "evaluation_split_is_now_exposed": True,
            "current_identity_reusable_for_confirmatory_model_evaluation": False,
        },
        "rows": rows,
    }


def validate_rule_gate_audit(audit: dict[str, Any], qualification_report: dict[str, Any]) -> dict[str, Any]:
    regenerated = generate_rule_gate_audit(qualification_report)
    if audit != regenerated:
        raise QualificationError("RuleGate audit 无法从资格 outcome matrix 确定重建")
    if audit["overall"] != {
        "state_count": 120,
        "safe_count": 120,
        "eligible_count": 120,
        "top1_safe_rate": 1.0,
        "direct_execution_coverage": 1.0,
        "wrong_direct_action_rate": 0.0,
    }:
        raise QualificationError("RuleGate 饱和指标漂移")
    if any(metrics["direct_execution_coverage"] != 1.0 or metrics["wrong_direct_action_rate"] != 0.0 for metrics in audit["by_build_system"].values()):
        raise QualificationError("RuleGate 未在三个构建系统同时饱和")
    if audit["phase_b_entry_gate"]["jev_entry_identifiable"] is not False:
        raise QualificationError("RuleGate 饱和时不应进入 Jev Provider 资格")
    return audit


def render_rule_gate_markdown(audit: dict[str, Any]) -> str:
    systems = "\n".join(
        f"| {name} | {audit['by_build_system'][name]['state_count']} | {audit['by_build_system'][name]['top1_safe_rate']:.4f} | "
        f"{audit['by_build_system'][name]['direct_execution_coverage']:.4f} | {audit['by_build_system'][name]['wrong_direct_action_rate']:.4f} |"
        for name in BUILD_SYSTEMS
    )
    splits = "\n".join(f"| {name} | {audit['by_split'][name]['state_count']} | {audit['by_split'][name]['direct_execution_coverage']:.4f} |" for name in SPLITS)
    v2_boundary = (
        "这不是 Jev 效果失败，因为本阶段没有调用 Jev。若继续该研究问题，必须建立新 identity："
        "在相同 coarse phase facts 下构造需要不同动作的多种失败根因，以候选动作后的冻结 continuation "
        "和严格终点决定标签，并使用新的未暴露项目族与时间后移 evaluation split。"
    )
    return f"""# Jev benchmark v1 RuleGate 可辨识性审计

- identity：`{audit["identity"]}`
- 来源资格报告 SHA-256：`{audit["source_qualification_report_sha256"]}`
- 决定：`{audit["decision"]}`

## 关键结果

`RuleGate` 只读取确定性 `phase_facts` 和可用动作族，不读取构建日志。在 120 个状态上，top-1 安全率、直接执行覆盖率均为 `1.0000`，错误直接动作率为 `0.0000`。

| 构建系统 | 状态 | top-1 安全率 | 直接覆盖率 | 错误率 |
|---|---:|---:|---:|---:|
{systems}

| split | 状态 | 直接覆盖率 |
|---|---:|---:|
{splits}

48 个状态有两个合格下一动作，72 个状态有一个合格下一动作。冻结的阶段 B 门槛要求 Jev 在相同风险下相对 RuleGate 增加至少 10 个百分点覆盖率；当前 RuleGate 覆盖率已为 100%，最大可能提升为 0 个百分点，因此该比较在 v1 上不可辨识。

## 研究决定

阶段 A 的“可执行且可重复”结论仍成立，但它没有证明 benchmark 足以评价语义路由。当前 v1 的状态被确定性阶段事实完全解出，语义日志没有产生增量决策空间。因此停止 Jev Provider 资格、controller 和端到端比较，不消费模型预算。

{v2_boundary}

本审计 Provider `0` 次、credential `0` 次、模型调用 `0` 次、模型 token `0`。
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
    subparsers.add_parser("audit-rule-gate")
    subparsers.add_parser("validate-rule-gate")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "generate":
        generate_contract_files()
        print(canonical_sha256(load_json(DEFAULT_MANIFEST)))
        return 0
    manifest, pool = load_contract()
    if args.command == "validate":
        print(canonical_sha256(manifest))
        return 0
    if args.command == "preflight":
        print(json.dumps(preflight(manifest, pool), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "run":
        report = run_qualification(
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
                    "decision": report["adjudication"]["decision"],
                },
                ensure_ascii=False,
            )
        )
        return 0 if report["status"] == "passed" else 2
    if args.command == "validate-report":
        report = validate_report(load_json(args.report), manifest, pool)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "decision": report["adjudication"]["decision"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "audit-rule-gate":
        qualification_report = validate_report(load_json(DEFAULT_JSON_REPORT), manifest, pool)
        audit = generate_rule_gate_audit(qualification_report)
        validate_rule_gate_audit(audit, qualification_report)
        if DEFAULT_RULE_GATE_JSON.exists() or DEFAULT_RULE_GATE_MARKDOWN.exists():
            raise QualificationError("RuleGate audit 已存在，禁止覆盖")
        write_once(
            DEFAULT_RULE_GATE_JSON,
            json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        write_once(DEFAULT_RULE_GATE_MARKDOWN, render_rule_gate_markdown(audit))
        print(json.dumps({"decision": audit["decision"]}, ensure_ascii=False))
        return 0
    if args.command == "validate-rule-gate":
        qualification_report = validate_report(load_json(DEFAULT_JSON_REPORT), manifest, pool)
        audit = validate_rule_gate_audit(load_json(DEFAULT_RULE_GATE_JSON), qualification_report)
        print(json.dumps({"decision": audit["decision"]}, ensure_ascii=False))
        return 0
    report = validate_report(load_json(args.report), manifest, pool)
    args.output.write_text(render_markdown(report), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Issue #451：Runtime v6 的 H0/H1/H2 held-out 零 Provider 资格。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
HARNESS_ROOT = REPO_ROOT / "backend/packages/harness"
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))

from deerflow.compile import agent_workflow_runtime_v3 as runtime_v3  # noqa: E402
from deerflow.compile import agent_workflow_runtime_v4 as runtime_v4  # noqa: E402
from deerflow.compile import agent_workflow_runtime_v6 as runtime_v6  # noqa: E402
from deerflow.compile import operations  # noqa: E402
from deerflow.compile.agent_workflow_schemas import SubmitCandidateRequest  # noqa: E402
from deerflow.compile.docker_runtime import CompileDockerRuntime  # noqa: E402
from deerflow.compile.manager import CompileSessionManager  # noqa: E402
from deerflow.compile.operations import CompileOperationsServices  # noqa: E402
from deerflow.compile.replay_closure_verifier import ReplayClosureVerifier  # noqa: E402
from deerflow.compile.schemas import BuildCommandRecord, CompileSession, utc_now_iso  # noqa: E402
from deerflow.config.paths import Paths  # noqa: E402

IDENTITY = "cpp-progress-aware-h0-h1-h2-runtime-v6-qualification-v1"
TRACKING_ISSUE = 451
BRANCH = "yiwei/451-h0-h1-h2-runtime-v6-qualification"
SCHEMA_ID = "forge-progress-aware-h0-h1-h2-runtime-v6-qualification-v1"
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests" / f"{IDENTITY}.json"
SCHEMA_PATH = REPO_ROOT / "benchmarks/schemas" / f"{SCHEMA_ID}.schema.json"
PREREGISTRATION_PATH = REPO_ROOT / "benchmarks/preregistrations" / f"{IDENTITY}.md"
SPEC_PATH = (
    REPO_ROOT
    / "docs/superpowers/specs/2026-10-14-h0-h1-h2-runtime-v6-qualification-design.md"
)
PLAN_PATH = (
    REPO_ROOT / "docs/superpowers/plans/2026-10-14-h0-h1-h2-runtime-v6-qualification.md"
)
EVIDENCE_ROOT = REPO_ROOT / ".compile-sessions" / f"benchmark-evidence-{IDENTITY}"
REPORT_JSON_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.json"
REPORT_MD_PATH = REPO_ROOT / "benchmarks/reports" / f"{IDENTITY}.md"
COMPILE_IMAGE = "autocompiler:gcc13"
IMAGE_ID = "sha256:d27a6ab733c7c3a9cbb5e4b32fb595aa5a422ff04bd212888d1041b90a2c4c2a"

FROZEN_COMPONENTS = {
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v3.py": "2d71383d011e943f78e9259b9f7ceec2c8e1f080d7609e86413ce188a841f65e",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v4.py": "48593cfea3a5cd0512531332bec89bc16afddbdc190605e55d17c027a7769c66",
    "backend/packages/harness/deerflow/compile/agent_workflow_runtime_v6.py": "70311ae3a598e183ba7450494629d8ee5a5e572c9e829f2d82a058122060406b",
    "backend/packages/harness/deerflow/compile/replay_closure_verifier.py": "01f8335ab0a586065803b34952b930adbf593624c611316b40ca2ccac685cd83",
    "backend/packages/harness/deerflow/compile/external_evaluator_v4.py": "9009c400b1b54d9ad05411f1a64124423cf50d8ba49bfa2d13071d9bedad4613",
}

TASKS = (
    {
        "task_id": "cmake-cmark",
        "project_family": "github.com/commonmark/cmark",
        "build_system": "cmake",
        "repository_url": "https://github.com/commonmark/cmark.git",
        "commit_sha": "7e1e10c32ca1275e387057606752123efc3e2793",
        "source_archive": {
            "sha256": "a150664a346a56651eedf8c8f5be0752b28a6d2b597b1686c045d87f86635118",
            "size": 268315,
        },
        "commands": (
            (
                "configure",
                "cmake -S . -B build -DBUILD_TESTING=OFF -DBUILD_SHARED_LIBS=OFF",
            ),
            ("build", "cmake --build build --parallel 2"),
            (
                "artifact_stage",
                "install -Dm644 build/src/libcmark.a /artifacts/lib/libcmark.a",
            ),
        ),
        "smoke": (
            "printf '%s\\n' '#include <cmark.h>' "
            '\'int main(void){ char *s=cmark_markdown_to_html("# Forge",7,0); '
            "if(!s)return 1; free(s); return 0; }' > /tmp/forge-cmark.c && "
            "cc -std=c11 -include stdlib.h -I/workspace/repo/src -I/workspace/repo/build/src "
            "/tmp/forge-cmark.c /artifacts/lib/libcmark.a -o /tmp/forge-cmark && /tmp/forge-cmark"
        ),
        "target": {
            "target_id": "cmark-static",
            "artifact_path": "lib/libcmark.a",
            "artifact_type": "static_library",
        },
    },
    {
        "task_id": "make-mpc",
        "project_family": "github.com/orangeduck/mpc",
        "build_system": "make",
        "repository_url": "https://github.com/orangeduck/mpc.git",
        "commit_sha": "1049534fc56b1971345c7aaa792dea55d6f9b7bc",
        "source_archive": {
            "sha256": "233e05300c875a93c8eca8f34092943ea74982c8731e57ef057b51278783ed7c",
            "size": 50683,
        },
        "commands": (
            ("build", "make -j2 libs"),
            (
                "artifact_stage",
                "install -Dm644 build/libmpc.a /artifacts/lib/libmpc.a",
            ),
        ),
        "smoke": (
            "printf '%s\\n' '#include <mpc.h>' "
            "'int main(void){mpc_parser_t *p=mpc_new(\"x\"); mpc_delete(p); return 0;}' "
            "> /tmp/forge-mpc.c && cc -std=c11 -I/workspace/repo /tmp/forge-mpc.c "
            "/artifacts/lib/libmpc.a -lm -o /tmp/forge-mpc && /tmp/forge-mpc"
        ),
        "target": {
            "target_id": "mpc-static",
            "artifact_path": "lib/libmpc.a",
            "artifact_type": "static_library",
        },
    },
    {
        "task_id": "autotools-expat",
        "project_family": "github.com/libexpat/libexpat",
        "build_system": "autotools",
        "repository_url": "https://github.com/libexpat/libexpat.git",
        "commit_sha": "ac140c2d34e0aafb1c6a126ca2917ff32d765518",
        "source_archive": {
            "sha256": "0ef33f1788fb624635e5a72cec85adf72d5daa84b8d2a871295080713c558d22",
            "size": 8487923,
        },
        "commands": (
            ("dependency", "cd expat && ./buildconf.sh"),
            (
                "configure",
                "cd expat && ./configure --disable-shared --enable-static --without-xmlwf --without-docbook",
            ),
            ("build", "make -C expat/lib -j2"),
            (
                "artifact_stage",
                "install -Dm644 expat/lib/.libs/libexpat.a /artifacts/lib/libexpat.a",
            ),
        ),
        "smoke": (
            "printf '%s\\n' '#include <expat.h>' "
            "'int main(void){XML_Parser p=XML_ParserCreate(0); if(!p)return 1; "
            "XML_ParserFree(p); return 0;}' > /tmp/forge-expat.c && cc -std=c11 "
            "-I/workspace/repo/expat/lib /tmp/forge-expat.c /artifacts/lib/libexpat.a "
            "-lm -o /tmp/forge-expat && /tmp/forge-expat"
        ),
        "target": {
            "target_id": "expat-static",
            "artifact_path": "lib/libexpat.a",
            "artifact_type": "static_library",
        },
    },
)


class QualificationError(RuntimeError):
    """资格身份、来源、生命周期或授权边界无效。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualificationError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise QualificationError(f"JSON 根必须是 object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_once_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise QualificationError(f"create-once 文件已存在: {path}") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _run(
    arguments: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 300,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        arguments,
        cwd=cwd,
        input=input_bytes,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[-2000:]
        raise QualificationError(
            f"命令失败: {arguments[0]} ({completed.returncode}): {detail}"
        )
    return completed


def generate_manifest() -> dict[str, Any]:
    return {
        "$schema": SCHEMA_ID,
        "schema_version": "1.0.0",
        "identity": IDENTITY,
        "issue": TRACKING_ISSUE,
        "branch": BRANCH,
        "status": "authorized_zero_provider_qualification",
        "authorization": {
            "public_source_network": True,
            "docker": True,
            "new_evidence_write": True,
            "credential_read": False,
            "provider_calls": False,
            "jev_calls": False,
            "model_tokens": 0,
            "formal_effect_attempts": 0,
            "historical_evidence_write": False,
            "replacement": False,
            "backfill": False,
            "dynamic_budget_controller": False,
        },
        "environment": {
            "compile_image": COMPILE_IMAGE,
            "image_id": IMAGE_ID,
            "parallel_jobs": 2,
            "build_network": "none",
        },
        "observed_basis": {
            "v3_identity": "cpp-progress-aware-harness-comparison-v3-authorized",
            "v3_decision": "stop_progress_aware_harness_as_primary_mechanism",
            "h0_arms": 27,
            "h0_budget_exhausted": 6,
            "h0_max_recorded_tokens": 337389,
            "h0_budget_exhausted_range": [308166, 337389],
            "maximum_response_recorded_tokens": 52297,
            "h2_identity": "cpp-progress-aware-replay-closure-qualification-v1",
            "h2_inventory_canonical_sha256": "0b13bf8a3ce869eb37a977246893aabf88172cc44a8828f4312c1076cd665fda",
            "runtime_v6_identity": "cpp-progress-aware-submit-rejection-recovery-gate-v1",
            "runtime_v6_inventory_canonical_sha256": "f3b70746664547aea75d0b9e699032c0f09fc4672be3f298098dd248a76cd47c",
            "runtime_v6_observed_project_excluded": "github.com/cesanta/mjson",
        },
        "future_common_budget": {
            "max_model_requests": 36,
            "max_recorded_tokens": 600000,
            "max_recorded_tokens_per_response": 100000,
            "authorized_recorded_tokens_per_arm": 700000,
            "max_agent_steps": 96,
            "max_tool_calls": 72,
            "max_commands": 48,
            "node_timeout_seconds": 1800,
            "command_timeout_seconds": 900,
            "evaluator_timeout_seconds": 1800,
            "replay_timeout_seconds": 1800,
            "cleanup_timeout_seconds": 120,
        },
        "treatments": {
            "h0": {
                "id": "h0_runtime_v3",
                "runtime": runtime_v3.AGENT_WORKFLOW_RUNTIME_VERSION,
            },
            "h1": {
                "id": "h1_runtime_v4",
                "runtime": runtime_v4.AGENT_WORKFLOW_RUNTIME_VERSION,
            },
            "h2": {
                "id": "h2_runtime_v6",
                "runtime": runtime_v6.AGENT_WORKFLOW_RUNTIME_VERSION,
                "increment_over_h1": "pre_freeze_replay_closure_and_bounded_submit_rejection_recovery",
            },
        },
        "screening": {
            "selection_mode": "repository_history_exclusion_then_source_only_entrypoint_screen",
            "prior_runtime_v6_project_excluded": "github.com/cesanta/mjson",
            "cmake_source_only_exclusion": {
                "project_family": "github.com/benhoyt/inih",
                "reason": "no_root_cmake_entrypoint",
            },
            "make_source_only_exclusion": {
                "project_family": "github.com/zserge/jsmn",
                "reason": "header_only_primary_artifact",
            },
            "selected_project_families_previously_absent_from_repository": True,
            "replacement_within_identity": False,
        },
        "tasks": [
            {
                **{
                    key: value for key, value in task.items() if key not in {"commands"}
                },
                "commands": [
                    {"role": role, "command": command, "timeout_seconds": 900}
                    for role, command in task["commands"]
                ],
            }
            for task in TASKS
        ],
        "qualification": {
            "q0_source_archives": 3,
            "q1_reference_closures": 3,
            "required_build_systems": ["cmake", "make", "autotools"],
            "pass_decision": "proceed_to_runtime_v6_three_arm_formal_comparison_design",
            "fail_decision": "stop_before_runtime_v6_three_arm_formal_comparison",
        },
        "future_effect_boundary": {
            "provider_canary_arms": 0,
            "provider_canary_enters_effect_estimate": False,
            "planned_formal_arms": 18,
            "formal_identity_required": True,
            "primary_estimand": "strict_success_risk_difference_h2_minus_h1",
            "noninferiority_margin": -0.1,
            "cluster_unit": "project_family",
            "replications_per_cell": 2,
        },
        "components": dict(FROZEN_COMPONENTS),
        "preregistration": {
            "path": str(PREREGISTRATION_PATH.relative_to(REPO_ROOT)),
            "sha256": _file_sha256(PREREGISTRATION_PATH),
        },
        "evidence_root": str(EVIDENCE_ROOT.relative_to(REPO_ROOT)),
    }


def schema_document(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "Forge H0/H1/H2 Runtime v6 held-out zero-provider qualification",
        "const": manifest or generate_manifest(),
    }


def validate_manifest(value: Any, *, verify_components: bool = True) -> dict[str, Any]:
    expected = generate_manifest()
    if not isinstance(value, dict) or value != expected:
        raise QualificationError("qualification manifest 发生漂移")
    schema = _load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(value)
    if verify_components:
        for relative, expected_sha256 in FROZEN_COMPONENTS.items():
            if _file_sha256(REPO_ROOT / relative) != expected_sha256:
                raise QualificationError(f"冻结组件漂移: {relative}")
    task_systems = {task["build_system"] for task in value["tasks"]}
    if task_systems != {"cmake", "make", "autotools"}:
        raise QualificationError("三构建系统覆盖漂移")
    families = [task["project_family"] for task in value["tasks"]]
    if len(families) != len(set(families)):
        raise QualificationError("项目族不唯一")
    budget = value["future_common_budget"]
    if budget["authorized_recorded_tokens_per_arm"] != (
        budget["max_recorded_tokens"] + budget["max_recorded_tokens_per_response"]
    ):
        raise QualificationError("未来 Token 授权上界不闭合")
    authorization = value["authorization"]
    if any(
        authorization[key] for key in ("credential_read", "provider_calls", "jev_calls")
    ):
        raise QualificationError("零 Provider 身份意外授权外部模型")
    if (
        authorization["model_tokens"] != 0
        or authorization["formal_effect_attempts"] != 0
    ):
        raise QualificationError("零 Provider 身份意外授权效果 observation")
    return value


def _git_text(*arguments: str) -> str:
    return _run(["git", *arguments], cwd=REPO_ROOT, timeout=60).stdout.decode().strip()


def preflight(
    manifest: dict[str, Any], *, require_absent_evidence: bool
) -> dict[str, Any]:
    validate_manifest(manifest)
    if _git_text("branch", "--show-current") != BRANCH:
        raise QualificationError("当前分支与 qualification identity 不一致")
    if _git_text("status", "--porcelain", "--untracked-files=no"):
        raise QualificationError("正式资格要求已跟踪 release 内容无修改")
    head = _git_text("rev-parse", "HEAD")
    remote_refs = set(_git_text("branch", "-r", "--contains", head).splitlines())
    if f"origin/{BRANCH}" not in {item.strip() for item in remote_refs}:
        raise QualificationError("资格 revision 尚未推送到同名远端分支")
    required = _run(
        [str(REPO_ROOT / "scripts/require-docker-runtime.sh")],
        cwd=REPO_ROOT,
        timeout=60,
    )
    if b"OK:" not in required.stdout:
        raise QualificationError("Docker runtime preflight 未返回成功")
    image_id = (
        _run(
            ["docker", "image", "inspect", COMPILE_IMAGE, "--format", "{{.Id}}"],
            timeout=60,
        )
        .stdout.decode()
        .strip()
    )
    if image_id != IMAGE_ID:
        raise QualificationError("Docker image identity 漂移")
    if require_absent_evidence and EVIDENCE_ROOT.exists():
        raise QualificationError("create-once evidence root 已存在")
    if _managed_containers():
        raise QualificationError("执行前存在 Forge 受管容器")
    return {
        "identity": IDENTITY,
        "release_revision": head,
        "manifest_sha256": _canonical_sha256(manifest),
        "runner_sha256": _file_sha256(SCRIPT_PATH),
        "preregistration_sha256": _file_sha256(PREREGISTRATION_PATH),
        "image_id": image_id,
        "credential_reads": 0,
        "provider_requests": 0,
        "model_tokens": 0,
        "formal_effect_attempts": 0,
    }


def _managed_containers(thread_id: str | None = None) -> list[str]:
    arguments = [
        "docker",
        "ps",
        "-aq",
        "--filter",
        "label=deerflow.compile.managed=true",
    ]
    if thread_id:
        arguments.extend(("--filter", f"label=deerflow.compile.thread_id={thread_id}"))
    output = _run(arguments, timeout=30).stdout.decode()
    return [line for line in output.splitlines() if line]


def _create_source_archive(task: dict[str, Any], destination: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix=f"forge-451-{task['task_id']}-"
    ) as temporary:
        clone = Path(temporary) / "repo"
        _run(
            [
                "git",
                "clone",
                "--no-tags",
                "--filter=blob:none",
                task["repository_url"],
                str(clone),
            ],
            timeout=300,
        )
        _run(
            ["git", "checkout", "--detach", task["commit_sha"]], cwd=clone, timeout=120
        )
        observed_commit = (
            _run(["git", "rev-parse", "HEAD"], cwd=clone).stdout.decode().strip()
        )
        if observed_commit != task["commit_sha"]:
            raise QualificationError(f"exact commit 漂移: {task['task_id']}")
        tar_bytes = _run(
            ["git", "archive", "--format=tar", "HEAD"],
            cwd=clone,
            timeout=120,
        ).stdout
        gzip_result = _run(["gzip", "-n"], input_bytes=tar_bytes, timeout=120)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(gzip_result.stdout)
    observed = {"sha256": _file_sha256(destination), "size": destination.stat().st_size}
    if observed != task["source_archive"]:
        raise QualificationError(f"source archive identity 漂移: {task['task_id']}")
    return observed


def _record_command(
    *,
    manager: CompileSessionManager,
    runtime: CompileDockerRuntime,
    session: CompileSession,
    task_id: str,
    index: int,
    role: str,
    command: str,
) -> BuildCommandRecord:
    started = utc_now_iso()
    result = runtime.exec(
        session,
        command,
        workdir="/workspace/repo",
        timeout_seconds=900,
        log_path=str(Path(session.leadagent_logs_dir) / f"{index:02d}-{role}.log"),
        strict_shell=True,
    )
    record = BuildCommandRecord(
        stage="bash",
        command=command,
        workdir="/workspace/repo",
        command_id=f"{task_id}-{index:02d}-{role}",
        role=role,
        timeout_seconds=900,
        timed_out=result.exit_code == 124,
        started_at=started,
        completed_at=utc_now_iso(),
        exit_code=result.exit_code,
        log_path=manager.relative_path(session, result.log_path or ""),
    )
    manager.record_command(session, record)
    if result.exit_code != 0:
        raise QualificationError(
            f"{task_id} {role} 失败: {result.combined_output[-2000:]}"
        )
    return record


def _run_q1_case(
    manifest: dict[str, Any],
    task: dict[str, Any],
    archive_path: Path,
    case_root: Path,
) -> dict[str, Any]:
    workspace_root = case_root / "workspace-root"
    paths = Paths(
        workspace_root=workspace_root, host_workspace_root=str(workspace_root)
    )
    manager = CompileSessionManager(
        paths=paths, default_image=COMPILE_IMAGE, parallel_jobs=2
    )
    runtime = CompileDockerRuntime(manager=manager)
    previous_services = operations._services
    operations._services = CompileOperationsServices(manager=manager, runtime=runtime)
    thread_id = f"issue-451-{task['task_id']}-{uuid.uuid4().hex[:8]}"
    session = manager.create_session(
        thread_id=thread_id,
        repo_url=task["repository_url"],
        image=COMPILE_IMAGE,
        run_id=f"qualification-{uuid.uuid4().hex}",
    )
    cleanup_succeeded = False
    started = time.monotonic()
    try:
        repo_dir = Path(session.leadagent_repo_dir)
        repo_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "r:gz") as archive:
            archive.extractall(repo_dir, filter="data")
        replay_source = Path(session.leadagent_repro_dir) / "source.tar"
        shutil.copy2(archive_path, replay_source)
        runtime.create_container(session)
        session.commit_sha = task["commit_sha"]
        session.selected_build_system = task["build_system"]
        session.executed_build_system = task["build_system"]
        session.replay_source_archive_sha256 = task["source_archive"]["sha256"]
        session.status = "inspected"
        manager.save_session(session)

        recipe_records: list[BuildCommandRecord] = []
        build_record: BuildCommandRecord | None = None
        for index, command in enumerate(task["commands"], start=1):
            record = _record_command(
                manager=manager,
                runtime=runtime,
                session=session,
                task_id=task["task_id"],
                index=index,
                role=command["role"],
                command=command["command"],
            )
            recipe_records.append(record)
            if record.role == "build":
                build_record = record
        if build_record is None:
            raise QualificationError(f"{task['task_id']} 缺少 supporting build")
        _record_command(
            manager=manager,
            runtime=runtime,
            session=session,
            task_id=task["task_id"],
            index=len(task["commands"]) + 1,
            role="smoke",
            command=task["smoke"],
        )
        target = task["target"]
        request = SubmitCandidateRequest(
            candidate_id=f"candidate-{task['task_id']}",
            build_system=task["build_system"],
            supporting_command_ids=(build_record.command_id,),
            artifact_paths=(target["artifact_path"],),
            target_mapping={target["target_id"]: target["artifact_path"]},
            recipe_command_ids=tuple(record.command_id for record in recipe_records),
            agent_summary="Issue #451 zero-provider Runtime v6 held-out qualification",
        )
        closure = ReplayClosureVerifier(timeout_seconds=1800).verify(
            request=request,
            session=session,
        )
        current = manager.load_session(session.session_id, session.thread_id)
        status_unchanged = (
            current.status == "inspected" and current.finalized_at is None
        )
        no_formal_replay_attempt = not current.replay_attempts
        ownership = runtime.exec(
            current,
            f"chown -R {os.getuid()}:{os.getgid()} /workspace /artifacts /logs",
            workdir="/",
            timeout_seconds=30,
        )
        if ownership.exit_code != 0:
            raise QualificationError(f"{task['task_id']} 无法恢复目录所有权")
        cleanup = runtime.stop_and_remove_container(current)
        cleanup_succeeded = cleanup.succeeded and cleanup.removed
        remaining = _managed_containers(thread_id)
        result = {
            "task_id": task["task_id"],
            "project_family": task["project_family"],
            "build_system": task["build_system"],
            "commit_sha": task["commit_sha"],
            "source_archive": task["source_archive"],
            "commands": len(recipe_records),
            "closure": closure.canonical_payload(),
            "status_unchanged": status_unchanged,
            "no_formal_replay_attempt": no_formal_replay_attempt,
            "cleanup_succeeded": cleanup_succeeded,
            "managed_containers_after_cleanup": remaining,
            "duration_milliseconds": round((time.monotonic() - started) * 1000),
            "credential_reads": 0,
            "provider_requests": 0,
            "model_tokens": 0,
            "formal_effect_attempts": 0,
        }
        _write_once_json(case_root / "result.json", result)
        return result
    finally:
        operations._services = previous_services
        if not cleanup_succeeded:
            try:
                runtime.stop_and_remove_container(session)
            except Exception:
                pass


def _phase_marker(phase: str) -> Path:
    return EVIDENCE_ROOT / phase / "attempt.json"


def _start_phase(phase: str, preflight_result: dict[str, Any]) -> None:
    _write_once_json(
        _phase_marker(phase),
        {
            "identity": IDENTITY,
            "phase": phase,
            "status": "started",
            "release_revision": preflight_result["release_revision"],
            "manifest_sha256": preflight_result["manifest_sha256"],
            "started_at": _now(),
            "completed_at": None,
            "error_class": None,
        },
    )


def _finish_phase(phase: str, status: str, error_class: str | None = None) -> None:
    path = _phase_marker(phase)
    marker = _load_json(path)
    if marker["status"] != "started":
        raise QualificationError(f"{phase} marker 已终结")
    marker.update(status=status, completed_at=_now(), error_class=error_class)
    _write_json(path, marker)


def execute(manifest: dict[str, Any]) -> dict[str, Any]:
    preflight_result = preflight(manifest, require_absent_evidence=True)
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=False)
    _write_once_json(EVIDENCE_ROOT / "identity.json", preflight_result)
    tasks = {task["task_id"]: task for task in manifest["tasks"]}
    q0_outcomes: list[dict[str, Any]] = []
    _start_phase("q0", preflight_result)
    try:
        for task in manifest["tasks"]:
            destination = EVIDENCE_ROOT / "q0/sources" / f"{task['task_id']}.tar.gz"
            observed = _create_source_archive(task, destination)
            q0_outcomes.append(
                {
                    "task_id": task["task_id"],
                    "project_family": task["project_family"],
                    "commit_sha": task["commit_sha"],
                    **observed,
                }
            )
        q0 = {
            "phase": "q0",
            "release_revision": preflight_result["release_revision"],
            "manifest_sha256": preflight_result["manifest_sha256"],
            "outcomes": q0_outcomes,
            "passed": len(q0_outcomes) == 3,
            "completed_at": _now(),
        }
        _write_once_json(EVIDENCE_ROOT / "q0/result.json", q0)
        _finish_phase("q0", "passed")
    except BaseException as exc:
        _write_once_json(
            EVIDENCE_ROOT / "q0/result.json",
            {
                "phase": "q0",
                "outcomes": q0_outcomes,
                "passed": False,
                "error_class": type(exc).__name__,
                "completed_at": _now(),
            },
        )
        _finish_phase("q0", "failed", type(exc).__name__)
        raise

    q1_outcomes: list[dict[str, Any]] = []
    _start_phase("q1", preflight_result)
    try:
        for task_id in ("cmake-cmark", "make-mpc", "autotools-expat"):
            task = tasks[task_id]
            q1_outcomes.append(
                _run_q1_case(
                    manifest,
                    task,
                    EVIDENCE_ROOT / "q0/sources" / f"{task_id}.tar.gz",
                    EVIDENCE_ROOT / "q1/cases" / task_id,
                )
            )
        bindings = {
            "h0_runtime_v3": runtime_v3.run_agent_workflow_node_v3.__name__,
            "h1_runtime_v4": runtime_v4.run_agent_workflow_node_v4.__name__,
            "h2_runtime_v6": runtime_v6.run_agent_workflow_node_v6.__name__,
        }
        passed = (
            len(q1_outcomes) == 3
            and all(item["closure"]["passed"] is True for item in q1_outcomes)
            and all(item["status_unchanged"] is True for item in q1_outcomes)
            and all(item["no_formal_replay_attempt"] is True for item in q1_outcomes)
            and all(item["cleanup_succeeded"] is True for item in q1_outcomes)
            and all(
                item["managed_containers_after_cleanup"] == [] for item in q1_outcomes
            )
            and bindings
            == {
                "h0_runtime_v3": "run_agent_workflow_node_v3",
                "h1_runtime_v4": "run_agent_workflow_node_v4",
                "h2_runtime_v6": "run_agent_workflow_node_v6",
            }
        )
        q1 = {
            "phase": "q1",
            "release_revision": preflight_result["release_revision"],
            "manifest_sha256": preflight_result["manifest_sha256"],
            "outcomes": q1_outcomes,
            "runtime_bindings": bindings,
            "passed": passed,
            "completed_at": _now(),
        }
        _write_once_json(EVIDENCE_ROOT / "q1/result.json", q1)
        _finish_phase("q1", "passed" if passed else "failed")
        if not passed:
            raise QualificationError("Q1 lifecycle 门禁未全部通过")
    except BaseException as exc:
        if not (EVIDENCE_ROOT / "q1/result.json").exists():
            _write_once_json(
                EVIDENCE_ROOT / "q1/result.json",
                {
                    "phase": "q1",
                    "outcomes": q1_outcomes,
                    "passed": False,
                    "error_class": type(exc).__name__,
                    "completed_at": _now(),
                },
            )
        if _load_json(_phase_marker("q1"))["status"] == "started":
            _finish_phase("q1", "failed", type(exc).__name__)
        raise
    return seal(manifest)


def _inventory(root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "inventory.json":
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": _file_sha256(path),
                }
            )
    return {
        "files": files,
        "file_count": len(files),
        "total_bytes": sum(item["size"] for item in files),
        "canonical_sha256": _canonical_sha256(files),
    }


def seal(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest)
    if (EVIDENCE_ROOT / "inventory.json").exists():
        raise QualificationError("inventory 已存在，禁止重新封存")
    q0 = _load_json(EVIDENCE_ROOT / "q0/result.json")
    q1 = _load_json(EVIDENCE_ROOT / "q1/result.json")
    if q0.get("passed") is not True or q1.get("passed") is not True:
        raise QualificationError("失败 identity 不能标记为通过")
    inventory = _inventory(EVIDENCE_ROOT)
    _write_once_json(EVIDENCE_ROOT / "inventory.json", inventory)
    return write_report(manifest, inventory=inventory)


def audit(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest)
    inventory = _load_json(EVIDENCE_ROOT / "inventory.json")
    expected = _inventory(EVIDENCE_ROOT)
    if inventory != expected:
        raise QualificationError("evidence inventory 漂移")
    q0 = _load_json(EVIDENCE_ROOT / "q0/result.json")
    q1 = _load_json(EVIDENCE_ROOT / "q1/result.json")
    zero_boundary = all(
        item.get("credential_reads") == 0
        and item.get("provider_requests") == 0
        and item.get("model_tokens") == 0
        and item.get("formal_effect_attempts") == 0
        for item in q1.get("outcomes", [])
    )
    valid = (
        q0.get("passed") is True
        and q1.get("passed") is True
        and len(q0.get("outcomes", [])) == 3
        and len(q1.get("outcomes", [])) == 3
        and zero_boundary
        and not _managed_containers()
    )
    return {
        "identity": IDENTITY,
        "valid": valid,
        "q0_passed": q0.get("passed"),
        "q1_passed": q1.get("passed"),
        "zero_provider_boundary": zero_boundary,
        "zero_managed_resources": not _managed_containers(),
        "inventory_canonical_sha256": inventory["canonical_sha256"],
        "file_count": inventory["file_count"],
        "total_bytes": inventory["total_bytes"],
        "decision": (
            manifest["qualification"]["pass_decision"]
            if valid
            else manifest["qualification"]["fail_decision"]
        ),
    }


def write_report(
    manifest: dict[str, Any], *, inventory: dict[str, Any] | None = None
) -> dict[str, Any]:
    inventory = inventory or _load_json(EVIDENCE_ROOT / "inventory.json")
    q0 = _load_json(EVIDENCE_ROOT / "q0/result.json")
    q1 = _load_json(EVIDENCE_ROOT / "q1/result.json")
    valid = q0.get("passed") is True and q1.get("passed") is True
    decision = (
        manifest["qualification"]["pass_decision"]
        if valid
        else manifest["qualification"]["fail_decision"]
    )
    report = {
        "schema_version": "1.0.0",
        "identity": IDENTITY,
        "status": "completed",
        "decision": decision,
        "passed": valid,
        "release_revision": q0["release_revision"],
        "manifest_sha256": q0["manifest_sha256"],
        "q0": {
            "source_archives": len(q0["outcomes"]),
            "passed": q0["passed"],
            "outcomes": q0["outcomes"],
        },
        "q1": {
            "reference_closures": len(q1["outcomes"]),
            "passed": q1["passed"],
            "runtime_bindings": q1["runtime_bindings"],
            "outcomes": q1["outcomes"],
        },
        "budget_design": manifest["future_common_budget"],
        "evidence_inventory": {
            "canonical_sha256": inventory["canonical_sha256"],
            "file_count": inventory["file_count"],
            "total_bytes": inventory["total_bytes"],
        },
        "authorization_observed": {
            "credential_reads": 0,
            "provider_requests": 0,
            "jev_requests": 0,
            "model_tokens": 0,
            "formal_effect_attempts": 0,
        },
        "interpretation_boundary": {
            "engineering_qualification_only": True,
            "treatment_effect": False,
            "success_rate_claim": False,
            "cost_claim": False,
            "h0_sufficient_budget_answered": False,
            "h2_incremental_effect_answered": False,
            "held_out_population_generalization": False,
        },
        "completed_at": _now(),
    }
    _write_json(REPORT_JSON_PATH, report)
    rows = "\n".join(
        f"| `{item['task_id']}` | {item['build_system']} | "
        f"`{item['closure']['classification']}` | "
        f"{item['closure']['duration_seconds']:.3f}s |"
        for item in q1["outcomes"]
    )
    markdown = f"""# Runtime v6 的 H0/H1/H2 held-out 零 Provider 资格结果

- Identity：`{IDENTITY}`
- 决定：`{decision}`
- Q0 source archive：`{len(q0["outcomes"])}/3`
- Q1 reference replay closure：`{len(q1["outcomes"])}/3`
- Evidence inventory：`{inventory["file_count"]}` files / `{inventory["total_bytes"]}` bytes
- Inventory canonical SHA-256：`{inventory["canonical_sha256"]}`

| 项目 | 构建系统 | closure | preflight 墙钟 |
| --- | --- | --- | --- |
{rows}

三臂绑定为 Runtime v3/v4/v6；未来共同预算冻结为 `T=600,000`、`R=100,000`。本结果只证明三个新项目的
确定性来源、reference recipe 和 H2 replay closure 在冻结环境中闭合。全程 0 credential、0 Provider、0 Jev、
0 model token、0 formal effect attempt。

本资格不回答 H0 在充足预算下能否成功，不证明 H2 相对 H1 提高严格成功率或降低成本。下一步只能创建独立的
18-arm H0/H1/H2 正式比较 identity，并在 Provider 前冻结 release、执行顺序、总预算与停止规则。
"""
    REPORT_MD_PATH.write_text(markdown, encoding="utf-8", newline="\n")
    return report


def plan(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest, verify_components=False)
    return {
        "identity": IDENTITY,
        "mode": "zero_provider_runtime_v6_held_out_qualification",
        "tasks": [task["task_id"] for task in manifest["tasks"]],
        "build_systems": [task["build_system"] for task in manifest["tasks"]],
        "treatments": manifest["treatments"],
        "future_common_budget": manifest["future_common_budget"],
        "authorization": manifest["authorization"],
        "decision_on_pass": manifest["qualification"]["pass_decision"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "generate",
            "validate",
            "plan",
            "preflight",
            "execute",
            "audit",
            "report",
        ),
    )
    arguments = parser.parse_args(argv)
    if arguments.command == "generate":
        manifest = generate_manifest()
        _write_json(MANIFEST_PATH, manifest)
        _write_json(SCHEMA_PATH, schema_document(manifest))
        payload: Any = {
            "manifest": str(MANIFEST_PATH.relative_to(REPO_ROOT)),
            "schema": str(SCHEMA_PATH.relative_to(REPO_ROOT)),
            "manifest_sha256": _canonical_sha256(manifest),
        }
    else:
        manifest = validate_manifest(_load_json(MANIFEST_PATH))
        if arguments.command == "validate":
            payload = {
                "status": "passed",
                "manifest_sha256": _canonical_sha256(manifest),
            }
        elif arguments.command == "plan":
            payload = plan(manifest)
        elif arguments.command == "preflight":
            payload = preflight(manifest, require_absent_evidence=True)
        elif arguments.command == "execute":
            payload = execute(manifest)
        elif arguments.command == "audit":
            payload = audit(manifest)
        else:
            payload = write_report(manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

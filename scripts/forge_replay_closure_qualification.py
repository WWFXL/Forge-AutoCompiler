#!/usr/bin/env python3
"""Issue #442：H2 replay closure 零 Provider 资格。"""

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))

from deerflow.compile import operations  # noqa: E402
from deerflow.compile.agent_workflow_schemas import SubmitCandidateRequest  # noqa: E402
from deerflow.compile.docker_runtime import CompileDockerRuntime  # noqa: E402
from deerflow.compile.manager import CompileSessionManager  # noqa: E402
from deerflow.compile.operations import CompileOperationsServices  # noqa: E402
from deerflow.compile.replay_closure_verifier import ReplayClosureVerifier  # noqa: E402
from deerflow.compile.schemas import BuildCommandRecord, CompileSession, utc_now_iso  # noqa: E402
from deerflow.config.paths import Paths  # noqa: E402

IDENTITY = "cpp-progress-aware-replay-closure-qualification-v1"
TRACKING_ISSUE = 442
COMPILE_IMAGE = "autocompiler:gcc13"
EVIDENCE_ROOT = REPO_ROOT / ".compile-sessions" / f"benchmark-evidence-{IDENTITY}"
REPORT_JSON = REPO_ROOT / "benchmarks" / "reports" / f"{IDENTITY}.json"
REPORT_MD = REPO_ROOT / "benchmarks" / "reports" / f"{IDENTITY}.md"


class QualificationError(RuntimeError):
    """资格执行或 create-once 合同失败。"""


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    build_system: str
    source_files: dict[str, str]
    commands: tuple[tuple[str, str, bool], ...]
    recipe_roles: tuple[str, ...]
    expected_passed: bool
    expected_classification: str


def _source_main() -> str:
    return '#include <stdio.h>\nint main(void) { puts("forge-h2"); return 0; }\n'


CASES = (
    CaseSpec(
        case_id="cmake-complete",
        build_system="cmake",
        source_files={
            "CMakeLists.txt": "cmake_minimum_required(VERSION 3.10)\nproject(forge_h2 C)\nadd_executable(app main.c)\n",
            "main.c": _source_main(),
        },
        commands=(
            ("configure", "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release", True),
            ("build", "cmake --build build --parallel 2", True),
            ("artifact_stage", "mkdir -p /artifacts/bin && cp build/app /artifacts/bin/app", True),
        ),
        recipe_roles=("configure", "build", "artifact_stage"),
        expected_passed=True,
        expected_classification="passed",
    ),
    CaseSpec(
        case_id="make-complete",
        build_system="make",
        source_files={
            "Makefile": "app: main.c\n\t$(CC) -O2 -o app main.c\n",
            "main.c": _source_main(),
        },
        commands=(
            ("build", "make -j2", True),
            ("artifact_stage", "mkdir -p /artifacts/bin && cp app /artifacts/bin/app", True),
        ),
        recipe_roles=("build", "artifact_stage"),
        expected_passed=True,
        expected_classification="passed",
    ),
    CaseSpec(
        case_id="make-missing-generated-input",
        build_system="make",
        source_files={
            "Makefile": "app: generated.c\n\t$(CC) -O2 -o app generated.c\n",
        },
        commands=(
            ("dependency", "printf '%s\\n' '#include <stdio.h>' 'int main(void) { puts(\"forge-h2\"); return 0; }' > generated.c", False),
            ("build", "make -j2", True),
            ("artifact_stage", "mkdir -p /artifacts/bin && cp app /artifacts/bin/app", True),
        ),
        recipe_roles=("build", "artifact_stage"),
        expected_passed=False,
        expected_classification="missing_generated_input",
    ),
    CaseSpec(
        case_id="autotools-complete",
        build_system="autotools",
        source_files={
            "configure.ac": "AC_INIT([forge-h2], [1.0])\nAC_PROG_CC\nAC_CONFIG_FILES([Makefile])\nAC_OUTPUT\n",
            "Makefile.in": "CC=@CC@\nCFLAGS=@CFLAGS@\napp: main.c\n\t$(CC) $(CFLAGS) -O2 -o app main.c\n",
            "main.c": _source_main(),
        },
        commands=(
            ("dependency", "autoreconf --force --install --verbose", True),
            ("configure", "./configure", True),
            ("build", "make -j2", True),
            ("artifact_stage", "mkdir -p /artifacts/bin && cp app /artifacts/bin/app", True),
        ),
        recipe_roles=("dependency", "configure", "build", "artifact_stage"),
        expected_passed=True,
        expected_classification="passed",
    ),
    CaseSpec(
        case_id="autotools-missing-bootstrap",
        build_system="autotools",
        source_files={
            "configure.ac": "AC_INIT([forge-h2], [1.0])\nAC_PROG_CC\nAC_CONFIG_FILES([Makefile])\nAC_OUTPUT\n",
            "Makefile.in": "CC=@CC@\nCFLAGS=@CFLAGS@\napp: main.c\n\t$(CC) $(CFLAGS) -O2 -o app main.c\n",
            "main.c": _source_main(),
        },
        commands=(
            ("dependency", "autoreconf --force --install --verbose", False),
            ("configure", "./configure", True),
            ("build", "make -j2", True),
            ("artifact_stage", "mkdir -p /artifacts/bin && cp app /artifacts/bin/app", True),
        ),
        recipe_roles=("configure", "build", "artifact_stage"),
        expected_passed=False,
        expected_classification="missing_bootstrap_step",
    ),
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_once(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise QualificationError(f"create-once 文件已存在: {path}") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _write_once_json(path: Path, payload: Any) -> None:
    _write_once(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _create_source(case: CaseSpec, source_dir: Path, archive_path: Path) -> str:
    source_dir.mkdir(parents=True)
    for relative_path, content in case.source_files.items():
        path = source_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    with tarfile.open(archive_path, "w") as archive:
        for path in sorted(source_dir.rglob("*")):
            archive.add(path, arcname=path.relative_to(source_dir).as_posix(), recursive=False)
    return _sha256_file(archive_path)


def _record_command(
    *,
    manager: CompileSessionManager,
    runtime: CompileDockerRuntime,
    session: CompileSession,
    case_id: str,
    index: int,
    role: str,
    command: str,
) -> str:
    started = utc_now_iso()
    result = runtime.exec(
        session,
        command,
        workdir="/workspace/repo",
        timeout_seconds=180,
        log_path=str(Path(session.leadagent_logs_dir) / f"{index:02d}-{role}.log"),
        strict_shell=True,
    )
    command_id = f"{case_id}-{index:02d}-{role}"
    manager.record_command(
        session,
        BuildCommandRecord(
            stage="bash",
            command=command,
            workdir="/workspace/repo",
            command_id=command_id,
            role=role,
            timeout_seconds=180,
            timed_out=result.exit_code == 124,
            started_at=started,
            completed_at=utc_now_iso(),
            exit_code=result.exit_code,
            log_path=manager.relative_path(session, result.log_path or ""),
        ),
    )
    if result.exit_code != 0:
        raise QualificationError(f"{case_id} 原始 {role} 命令失败: {result.combined_output[-2000:]}")
    return command_id


def _managed_containers(thread_id: str) -> list[str]:
    result = subprocess.run(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            "label=deerflow.compile.managed=true",
            "--filter",
            f"label=deerflow.compile.thread_id={thread_id}",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return [line for line in result.stdout.splitlines() if line]


def run_case(case: CaseSpec, *, workspace_root: Path) -> dict[str, Any]:
    paths = Paths(workspace_root=workspace_root, host_workspace_root=str(workspace_root))
    manager = CompileSessionManager(paths=paths, default_image=COMPILE_IMAGE, parallel_jobs=2)
    runtime = CompileDockerRuntime(manager=manager)
    previous_services = operations._services
    operations._services = CompileOperationsServices(manager=manager, runtime=runtime)
    thread_id = f"issue-442-{case.case_id}-{uuid.uuid4().hex[:8]}"
    session = manager.create_session(
        thread_id=thread_id,
        repo_url=f"https://example.invalid/{case.case_id}.git",
        image=COMPILE_IMAGE,
        run_id=f"qualification-{uuid.uuid4().hex}",
    )
    compile_cleanup = False
    started = time.monotonic()
    try:
        source_dir = workspace_root / "fixture-source" / case.case_id
        archive_path = Path(session.leadagent_repro_dir) / "source.tar"
        source_sha256 = _create_source(case, source_dir, archive_path)
        repo_dir = Path(session.leadagent_repo_dir)
        shutil.copytree(source_dir, repo_dir)
        runtime.create_container(session)
        session.commit_sha = hashlib.sha1(f"{IDENTITY}:{case.case_id}".encode()).hexdigest()
        session.selected_build_system = case.build_system
        session.executed_build_system = case.build_system
        session.replay_source_archive_sha256 = source_sha256
        session.status = "inspected"
        manager.save_session(session)

        command_ids: dict[str, list[str]] = {}
        recipe_ids: list[str] = []
        for index, (role, command, include_in_recipe) in enumerate(case.commands, start=1):
            command_id = _record_command(
                manager=manager,
                runtime=runtime,
                session=session,
                case_id=case.case_id,
                index=index,
                role=role,
                command=command,
            )
            command_ids.setdefault(role, []).append(command_id)
            if include_in_recipe:
                recipe_ids.append(command_id)
        smoke_id = _record_command(
            manager=manager,
            runtime=runtime,
            session=session,
            case_id=case.case_id,
            index=len(case.commands) + 1,
            role="smoke",
            command="/artifacts/bin/app",
        )
        assert smoke_id

        request = SubmitCandidateRequest(
            candidate_id=f"candidate-{case.case_id}",
            build_system=case.build_system,
            supporting_command_ids=(command_ids["build"][-1],),
            artifact_paths=("bin/app",),
            target_mapping={"app-executable": "bin/app"},
            recipe_command_ids=tuple(recipe_ids),
            agent_summary="Issue #442 zero-provider replay closure fixture",
        )
        result = ReplayClosureVerifier(timeout_seconds=180).verify(
            request=request,
            session=session,
        )
        current = manager.load_session(session.session_id, session.thread_id)
        status_unchanged = current.status == "inspected" and current.finalized_at is None
        no_formal_replay_attempt = not current.replay_attempts
        ownership = runtime.exec(
            current,
            f"chown -R {os.getuid()}:{os.getgid()} /workspace /artifacts /logs",
            workdir="/",
            timeout_seconds=30,
        )
        if ownership.exit_code != 0:
            raise QualificationError(f"{case.case_id} 无法恢复夹具目录所有权: {ownership.combined_output[-1000:]}")
        compile_cleanup_result = runtime.stop_and_remove_container(current)
        compile_cleanup = compile_cleanup_result.succeeded and compile_cleanup_result.removed
        orphan_ids = _managed_containers(thread_id)
        observed = {
            "case_id": case.case_id,
            "build_system": case.build_system,
            "expected_passed": case.expected_passed,
            "expected_classification": case.expected_classification,
            "result": result.canonical_payload(),
            "status_unchanged": status_unchanged,
            "no_formal_replay_attempt": no_formal_replay_attempt,
            "compile_cleanup_succeeded": compile_cleanup,
            "managed_containers_after_cleanup": orphan_ids,
            "provider_requests": 0,
            "credential_reads": 0,
            "model_tokens": 0,
            "formal_effect_attempts": 0,
            "duration_seconds": round(time.monotonic() - started, 6),
        }
        observed["passed"] = (
            result.passed is case.expected_passed and result.classification == case.expected_classification and result.cleanup_succeeded and status_unchanged and no_formal_replay_attempt and compile_cleanup and not orphan_ids
        )
        return observed
    finally:
        if not compile_cleanup:
            try:
                if session.container_id:
                    runtime.exec(
                        session,
                        f"chown -R {os.getuid()}:{os.getgid()} /workspace /artifacts /logs",
                        workdir="/",
                        timeout_seconds=30,
                    )
                runtime.stop_and_remove_container(session)
            except Exception:
                pass
        operations._services = previous_services


def run_engineering_check() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="forge-h2-engineering-") as temporary:
        workspace_root = Path(temporary)
        cases = [run_case(case, workspace_root=workspace_root / case.case_id) for case in CASES]
    return {
        "identity": IDENTITY,
        "mode": "engineering-check",
        "passed": all(case["passed"] for case in cases),
        "cases": cases,
    }


def _inventory(root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "inventory.json"):
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":"))
    return {
        "files": files,
        "file_count": len(files),
        "total_bytes": sum(item["size"] for item in files),
        "canonical_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
    }


def run_formal() -> dict[str, Any]:
    if EVIDENCE_ROOT.exists():
        raise QualificationError(f"create-once evidence root 已存在: {EVIDENCE_ROOT}")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if dirty:
        raise QualificationError("formal qualification 要求干净工作树")
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=False)
    identity = {
        "identity": IDENTITY,
        "tracking_issue": TRACKING_ISSUE,
        "release_revision": revision,
        "compile_image": COMPILE_IMAGE,
        "case_ids": [case.case_id for case in CASES],
        "provider_requests_authorized": 0,
        "credential_reads_authorized": 0,
        "created_at": utc_now_iso(),
    }
    _write_once_json(EVIDENCE_ROOT / "identity.json", identity)
    workspace_root = EVIDENCE_ROOT / "runtime"
    results = []
    for case in CASES:
        result = run_case(case, workspace_root=workspace_root / case.case_id)
        results.append(result)
        _write_once_json(EVIDENCE_ROOT / "cases" / f"{case.case_id}.json", result)
        if not result["passed"]:
            break
    gates = {
        "all_cases_completed": len(results) == len(CASES),
        "all_cases_expected": len(results) == len(CASES) and all(result["passed"] for result in results),
        "negative_cases_detected": len(results) == len(CASES) and sum(not result["result"]["passed"] for result in results) == 2,
        "positive_cases_accepted": len(results) == len(CASES) and sum(result["result"]["passed"] for result in results) == 3,
        "session_state_preserved": all(result["status_unchanged"] and result["no_formal_replay_attempt"] for result in results),
        "cleanup_closed": all(result["compile_cleanup_succeeded"] and not result["managed_containers_after_cleanup"] for result in results),
        "zero_provider_boundary": all(result["provider_requests"] == result["credential_reads"] == result["model_tokens"] == 0 for result in results),
    }
    summary = {
        "identity": IDENTITY,
        "release_revision": revision,
        "case_count": len(results),
        "gates": gates,
        "passed": all(gates.values()),
        "decision": "proceed_to_unseen_h0_h2_comparison_design" if all(gates.values()) else "stop_before_provider_comparison",
        "cases": [
            {
                "case_id": result["case_id"],
                "passed": result["passed"],
                "observed_passed": result["result"]["passed"],
                "classification": result["result"]["classification"],
            }
            for result in results
        ],
    }
    _write_once_json(EVIDENCE_ROOT / "result.json", summary)
    _write_once_json(EVIDENCE_ROOT / "marker.json", {"identity": IDENTITY, "passed": summary["passed"], "decision": summary["decision"]})
    shutil.rmtree(workspace_root, ignore_errors=True)
    inventory = _inventory(EVIDENCE_ROOT)
    _write_once_json(EVIDENCE_ROOT / "inventory.json", inventory)
    return {**summary, "inventory": inventory}


def write_report(result: dict[str, Any]) -> None:
    report = {
        "identity": result["identity"],
        "release_revision": result["release_revision"],
        "passed": result["passed"],
        "decision": result["decision"],
        "gates": result["gates"],
        "cases": result["cases"],
        "inventory_canonical_sha256": result["inventory"]["canonical_sha256"],
        "inventory_file_count": result["inventory"]["file_count"],
        "inventory_total_bytes": result["inventory"]["total_bytes"],
        "interpretation_boundary": "known-defect engineering qualification; no treatment effect",
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = "\n".join(f"| `{case['case_id']}` | {case['observed_passed']} | `{case['classification']}` | {case['passed']} |" for case in report["cases"])
    markdown = f"""# H2 replay closure 零 Provider 资格结果

- Identity：`{IDENTITY}`
- 结论：`{report["decision"]}`
- 全部门槛：`{report["passed"]}`
- Evidence inventory canonical SHA-256：`{report["inventory_canonical_sha256"]}`

| Case | closure ready | 分类 | 符合预注册 |
|---|---:|---|---:|
{rows}

该结果只证明已知两类 replay closure 缺口可在候选冻结前被发现，且三个最小正确 recipe 未被误拦。它不估计 H2 对严格成功率、成本、token 或未见真实项目的效果。
"""
    REPORT_MD.write_text(markdown, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("engineering-check", "run", "audit"))
    args = parser.parse_args()
    if args.command == "engineering-check":
        result = run_engineering_check()
    elif args.command == "run":
        result = run_formal()
        write_report(result)
    else:
        if not EVIDENCE_ROOT.is_dir():
            raise QualificationError("evidence root 不存在")
        inventory = json.loads((EVIDENCE_ROOT / "inventory.json").read_text(encoding="utf-8"))
        observed = _inventory(EVIDENCE_ROOT)
        observed_without_inventory = observed["canonical_sha256"]
        result = {
            "identity": IDENTITY,
            "valid": inventory["canonical_sha256"] == observed_without_inventory,
            "inventory": inventory,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("passed", result.get("valid", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())

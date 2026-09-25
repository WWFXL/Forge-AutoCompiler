#!/usr/bin/env python3
"""执行 Phase 5 v2 的六项目 0 Provider build-system qualification。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", SCRIPT_ROOT.parent)).resolve()
HARNESS_ROOT = REPO_ROOT / "backend" / "packages" / "harness"
for import_root in (str(HARNESS_ROOT), str(SCRIPT_ROOT)):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

import forge_agent_workflow_stage_b_phase5_v2_qualification_protocol as protocol  # noqa: E402

from deerflow.compile.operations import (  # noqa: E402
    cleanup_and_finalize_compile_session_impl,
    clone_repository_impl,
    inspect_build_system_impl,
    prepare_compile_session_impl,
)

MANAGED_CONTAINER_PREFIXES = ("deerflow-compile-", "deerflow-replay-")
DEFAULT_OUTPUT = Path("/tmp/forge-phase5-v2-build-system-qualification.json")


class Phase5V2QualificationRunnerError(RuntimeError):
    """Phase 5 v2 qualification 环境、探测或 cleanup 无效。"""


def _run_checked(command: Sequence[str], failure: str, *, cwd: Path | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise Phase5V2QualificationRunnerError(failure)
    return result.stdout.strip()


def _git(*arguments: str) -> str:
    return _run_checked(["git", "-c", f"safe.directory={REPO_ROOT}", *arguments], "无法核验 qualification release identity", cwd=REPO_ROOT)


def require_release_identity() -> str:
    branch = _git("branch", "--show-current")
    revision = _git("rev-parse", "HEAD")
    origin_main = _git("rev-parse", "origin/main")
    dirty = _git("status", "--porcelain", "--untracked-files=normal")
    if branch != "main" or revision != origin_main or dirty:
        raise Phase5V2QualificationRunnerError("qualification 要求干净 main == origin/main")
    return revision


def require_image_identity(plan: dict[str, Any]) -> str:
    actual = _run_checked(
        ["docker", "image", "inspect", plan["environment"]["compile_image"], "--format", "{{.Id}}"],
        "无法读取 qualification 编译镜像",
    )
    if actual != plan["environment"]["image_id"]:
        raise Phase5V2QualificationRunnerError("qualification Docker image ID 与冻结 plan 不一致")
    return actual


def require_zero_managed_resources() -> None:
    names = _run_checked(["docker", "ps", "-a", "--format", "{{.Names}}"], "无法核验受管容器")
    managed = sorted(name for name in names.splitlines() if name.startswith(MANAGED_CONTAINER_PREFIXES))
    if managed:
        raise Phase5V2QualificationRunnerError(f"存在 Compile Session/replay orphan: {','.join(managed)}")
    paused = _run_checked(
        ["docker", "ps", "-q", "--filter", "status=paused", "--filter", "label=deerflow.compile.managed=true"],
        "无法核验 paused parent",
    )
    managed_images = _run_checked(
        ["docker", "images", "-q", "--filter", "label=deerflow.compile.managed=true"],
        "无法核验受管镜像",
    )
    if paused or managed_images:
        raise Phase5V2QualificationRunnerError("存在 paused parent 或受管镜像")


def collect_preflight(plan: dict[str, Any]) -> dict[str, Any]:
    protocol.validate_plan(plan, REPO_ROOT)
    revision = require_release_identity()
    image_id = require_image_identity(plan)
    require_zero_managed_resources()
    return {
        "release_revision": revision,
        "image_id": image_id,
        "qualification_plan_sha256": protocol.canonical_sha256(plan),
    }


def _qualify_task(plan: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    plan_digest = protocol.canonical_sha256(plan)
    task_id = task["task_id"]
    thread_id = f"phase5-v2-qualification-{task_id}-{uuid.uuid4().hex[:12]}"
    session = None
    cleanup_succeeded = False
    try:
        session = prepare_compile_session_impl(
            thread_id=thread_id,
            repo_url=task["repository_url"],
            run_id=f"phase5-v2-qualification-{plan_digest[:12]}-{task_id}-{uuid.uuid4().hex}",
            task_description=f"Phase 5 v2 build-system qualification: {task_id}",
        )
        if session.image != plan["environment"]["compile_image"] or session.image_id != plan["environment"]["image_id"]:
            raise Phase5V2QualificationRunnerError(f"{task_id} compile image identity 发生漂移")
        clone, _message = clone_repository_impl(
            session=session,
            repo_url=task["repository_url"],
            commit_sha=task["commit_sha"],
            depth=1,
            max_retries=1,
        )
        if clone.exit_code != 0 or session.commit_sha != task["commit_sha"]:
            raise Phase5V2QualificationRunnerError(f"{task_id} exact commit checkout 失败")
        primary, detected, suggested = inspect_build_system_impl(session=session)
        capabilities = list(session.build_system_capabilities)
        if primary == "unknown" or not capabilities or primary != capabilities[0]:
            raise Phase5V2QualificationRunnerError(f"{task_id} 未得到可冻结的 build-system selection")
        result = {
            "task_id": task_id,
            "repository_url": task["repository_url"],
            "commit_sha": task["commit_sha"],
            "historical_build_system_label": task["historical_build_system_label"],
            "build_system_capabilities": capabilities,
            "selected_build_system": primary,
            "detected_markers": [
                {"build_system": build_system, "marker": marker}
                for build_system, marker in detected
            ],
            "suggested_commands": suggested,
            "session_id": session.session_id,
            "session_metadata_path": session.metadata_path,
        }
        return result
    finally:
        if session is not None:
            _finalized, cleanup = cleanup_and_finalize_compile_session_impl(
                session=session,
                interrupted_status="cancelled",
                error="Phase 5 v2 build-system qualification completed without a build attempt.",
            )
            cleanup_succeeded = cleanup.succeeded
        require_zero_managed_resources()
        if session is not None and not cleanup_succeeded:
            raise Phase5V2QualificationRunnerError(f"{task_id} qualification cleanup 失败")


def execute(plan: dict[str, Any], *, output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    preflight = collect_preflight(plan)
    tasks: list[dict[str, Any]] = []
    for task in plan["tasks"]:
        result = _qualify_task(plan, task)
        result["cleanup_succeeded"] = True
        tasks.append(result)
    require_zero_managed_resources()
    qualification = {
        "schema_version": protocol.RESULT_SCHEMA_VERSION,
        "document_type": protocol.RESULT_DOCUMENT_TYPE,
        "status": "passed",
        "qualification_plan_sha256": preflight["qualification_plan_sha256"],
        "release_revision": preflight["release_revision"],
        "image": plan["environment"]["compile_image"],
        "image_id": preflight["image_id"],
        "provider_request_count": 0,
        "model_created": False,
        "formal_attempt_created": False,
        "zero_managed_resources_before": True,
        "zero_managed_resources_after": True,
        "tasks": tasks,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    protocol.validate_result(qualification, plan)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(qualification, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    except FileExistsError as exc:
        raise Phase5V2QualificationRunnerError(f"qualification output 已存在，拒绝覆盖: {output}") from exc
    return qualification


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "run", "validate-result"))
    parser.add_argument("--plan", type=Path, default=REPO_ROOT / protocol.PLAN_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    plan = protocol.load_plan(args.plan, REPO_ROOT)
    if args.command == "preflight":
        result: Any = collect_preflight(plan)
    elif args.command == "run":
        result = execute(plan, output=args.output)
    else:
        result = protocol.validate_result(protocol._load_json(args.output), plan)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

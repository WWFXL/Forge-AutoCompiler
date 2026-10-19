#!/usr/bin/env python3
"""扩展来源的完整参考任务资格；失败不替换，不调用模型。"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
import tarfile
import time
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "backend/packages/harness"), str(REPO_ROOT / "scripts")]

from forge_build_plan_agent_canary import unchanged  # noqa: E402
from forge_build_source_expansion import inspect_archive  # noqa: E402
from forge_typed_evidence import audit, digest, seal, write_json  # noqa: E402

from deerflow.compile import operations  # noqa: E402
from deerflow.compile.docker_runtime import CompileDockerRuntime, RuntimeConfig  # noqa: E402
from deerflow.compile.manager import CompileSessionManager  # noqa: E402
from deerflow.compile.plan_cross_system import before_deadline  # noqa: E402
from deerflow.compile.plan_workflow import BuildPlan, PlanBudget, PlanWorkflow  # noqa: E402
from deerflow.config.paths import Paths  # noqa: E402


def normalized_source(source, destination, limits):
    """仅移除codeload的外层目录；普通文件字节和符号链接文本不变。"""
    inspected = inspect_archive(source, limits)
    prefix = inspected["archive_root"] + "/"
    with tarfile.open(source, "r:gz") as original, tarfile.open(destination, "x") as output:
        for member in original:
            if member.name.rstrip("/") == prefix.rstrip("/"):
                continue
            adjusted = copy.copy(member)
            adjusted.name = member.name[len(prefix) :]
            adjusted.pax_headers = {}
            if member.islnk():
                adjusted.linkname = member.linkname[len(prefix) :]
            output.addfile(adjusted, original.extractfile(member) if member.isfile() else None)
    return {row["path"]: row["sha256"] for row in inspected["entries"] if row["type"] == "file"}


def run_reference(item, folder, protocol):
    folder.mkdir(exist_ok=False)
    plan = BuildPlan.model_validate(item["plan"])
    archive = Path(item["source_archive"])
    if digest(archive) != plan.source_archive_sha256:
        raise ValueError("参考任务归档身份变化")
    hashes_path = Path(item["source_file_hashes_path"])
    if digest(hashes_path) != item["source_file_hashes_sha256"]:
        raise ValueError("原始源码索引身份变化")
    frozen = json.loads(hashes_path.read_text())
    write_json(folder / "original-source-hashes.json", frozen)
    paths = Paths(base_dir=folder / "data", workspace_root=folder, host_workspace_root=str(folder))
    manager = CompileSessionManager(paths=paths, default_image=plan.image_id, parallel_jobs=2)
    runtime = CompileDockerRuntime(manager=manager, config=RuntimeConfig(image=plan.image_id, parallel_jobs=2, replay_timeout_seconds=protocol["replay_timeout_seconds"]))
    session = manager.create_session("reference-expansion", plan.repository_url, image=plan.image_id)
    original_services = operations._services
    operations._services = operations.CompileOperationsServices(manager=manager, runtime=runtime)
    result = {"name": item["name"], "status": "started", "qualified": False, "provider_calls": 0}
    started = time.monotonic()
    source = Path(session.leadagent_repo_dir)
    try:
        source.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as handle:
            handle.extractall(source, filter="data")
        unchanged(source, frozen)
        shutil.copyfile(archive, Path(session.leadagent_repro_dir) / "source.tar")
        session.commit_sha, session.image_id = plan.commit_sha, plan.image_id
        session.replay_source_archive_sha256 = plan.source_archive_sha256
        session.build_system = session.selected_build_system = plan.build_system
        try:
            runtime.create_container(session)
        finally:
            manager.save_session(session)
        session.status = "inspected"
        manager.save_session(session)
        workflow = PlanWorkflow(plan=plan, session=session, manager=manager, runtime=runtime, budget=PlanBudget(**protocol["plan_budget"]))
        state = workflow.run()
        result["initial"] = state
        if state["status"] == "ready_for_verification":
            state = workflow.verify()
        result.update(status=state["status"], final=state)
        unchanged(source, frozen)
        result["fixed_source_files_unchanged"] = True
    except Exception as exc:
        result.update(status="stopped", error_class=type(exc).__name__, error=str(exc)[:1000])
    finally:
        try:
            current = manager.load_session(session.session_id, session.thread_id)
            current, cleanup = operations.cleanup_and_finalize_compile_session_impl(session=current)
            result.update(cleanup=asdict(cleanup), session_status=current.status, session_id=current.session_id)
        except Exception as exc:
            result.update(cleanup={"succeeded": False}, cleanup_error_class=type(exc).__name__)
        finally:
            try:
                unchanged(source, frozen)
                result["fixed_source_files_unchanged"] = True
            except ValueError as exc:
                result.update(fixed_source_files_unchanged=False, source_error_class=type(exc).__name__)
            operations._services = original_services
            result["elapsed_seconds"] = time.monotonic() - started
            result["qualified"] = result["status"] == "verified" and result.get("session_status") == "completed" and result["cleanup"]["succeeded"] and result.get("fixed_source_files_unchanged", False)
            write_json(folder / "result.json", result)
    return result


def execute_schedule(protocol, root, executor=run_reference):
    results = []
    for item in protocol["projects"]:
        try:
            before_deadline(protocol["deadline_utc"], 3000)
        except ValueError:
            results.append({"name": item["name"], "status": "not_started_deadline", "qualified": False, "provider_calls": 0})
            continue
        try:
            result = executor(item, root / item["name"], protocol)
        except Exception as exc:
            result = {"name": item["name"], "status": "infrastructure_stopped", "error_class": type(exc).__name__, "qualified": False, "cleanup": {"succeeded": False}, "provider_calls": 0}
        results.append(result)
        print(json.dumps({key: result.get(key) for key in ("name", "status", "qualified", "session_status", "elapsed_seconds")}), flush=True)
        if not result["cleanup"]["succeeded"]:
            break
    return results


def validate(protocol):
    if protocol["identity"] != "cpp-build-reference-expansion-v1" or protocol["provider_calls"] != 0 or len(protocol["projects"]) != 10:
        raise ValueError("完整参考任务身份或边界不符")
    before_deadline(protocol["deadline_utc"], 3000)
    parent = audit(Path(protocol["catalog_root"]))
    if parent["inventory_canonical_sha256"] != protocol["catalog_inventory_sha256"]:
        raise ValueError("来源目录身份变化")
    for name, expected in protocol["components"].items():
        if digest(REPO_ROOT / name) != expected:
            raise ValueError("参考资格组件变化")
    for item in protocol["projects"]:
        plan = BuildPlan.model_validate(item["plan"])
        if digest(Path(item["source_archive"])) != plan.source_archive_sha256:
            raise ValueError("参考源码归档变化")
        if digest(Path(item["source_file_hashes_path"])) != item["source_file_hashes_sha256"]:
            raise ValueError("原始源码索引变化")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    validate(protocol)
    if args.validate_only:
        print(json.dumps({"valid": True, "provider_calls": 0}))
        return 0
    subprocess.run(["bash", str(REPO_ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "protocol.json").write_bytes(args.protocol.read_bytes())
    results = []
    try:
        results = execute_schedule(protocol, root)
    finally:
        write_json(root / "result.json", {"identity": protocol["identity"], "kind": "zero_provider_reference_qualification", "provider_calls": 0, "projects": results})
        print(json.dumps(seal(root, protocol, REPO_ROOT)), flush=True)
    return 0 if len(results) == 10 and all(row["qualified"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

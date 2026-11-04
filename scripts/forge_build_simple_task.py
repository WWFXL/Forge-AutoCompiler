#!/usr/bin/env python3
"""简洁任务零Provider实跑入口：独立公开输入/参考/脚本方案，不作模型效果比较。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/packages/harness"))

from deerflow.compile import operations  # noqa: E402
from deerflow.compile.docker_runtime import CompileDockerRuntime, RuntimeConfig  # noqa: E402
from deerflow.compile.manager import CompileSessionManager  # noqa: E402
from deerflow.compile.plan_workflow import PlanBudget  # noqa: E402
from deerflow.compile.simple_build_runtime import SimpleBuildWorkflow  # noqa: E402
from deerflow.compile.simple_build_task import BuildReference, PublicBuildTask, assemble_simple_plan, simple_agent_packet  # noqa: E402
from deerflow.compile.unified_plan_equivalent_observed import ObservedBuildActions  # noqa: E402
from deerflow.config.paths import Paths  # noqa: E402


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def full_completion(layers, cleanup):
    values = [layers["primary_build_completed"], cleanup]
    for key in ("delivery", "author_tests", "clean_replay"):
        status = layers[key]
        values.append(True if status in {"passed", "not_applicable"} else None if status == "unobserved" else False)
    return False if False in values else None if None in values else True


def run(*, task, reference, actions, source_archive, output_root, repair_actions=None, author_test_seconds=60, replay_seconds=180):
    subprocess.run(["bash", str(ROOT / "scripts/require-docker-runtime.sh")], check=True, timeout=30)
    if hashlib.sha256(source_archive.read_bytes()).hexdigest() != task.source_archive_sha256:
        raise ValueError("源码归档与公开任务不一致")
    root = output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    save(
        root / "scope.json",
        dict(
            kind="zero_provider_simple_build_engineering",
            provider_calls=0,
            task=task.model_dump(mode="json"),
            reference=reference.model_dump(mode="json"),
            actions=actions.model_dump(mode="json"),
            scripted_repair=repair_actions is not None,
            budget=PlanBudget(wall_clock_seconds=600, command_timeout_seconds=180).model_dump(),
            author_test_seconds=author_test_seconds,
            replay_seconds=replay_seconds,
        ),
    )
    save(root / "initial-agent-packet.json", simple_agent_packet(task))
    paths = Paths(base_dir=root / "data", workspace_root=root, host_workspace_root=str(root))
    manager = CompileSessionManager(paths=paths, default_image=task.image_id, parallel_jobs=task.parallel_jobs)
    runtime = CompileDockerRuntime(manager=manager, config=RuntimeConfig(image=task.image_id, parallel_jobs=task.parallel_jobs, replay_timeout_seconds=replay_seconds))
    session = manager.create_session("simple-build-engineering", task.repository_url, image=task.image_id)
    original = operations._services
    operations._services = operations.CompileOperationsServices(manager=manager, runtime=runtime)
    result = dict(kind="zero_provider_engineering", provider_calls=0, runtime_agent_calls=0, status="started")
    workflow = None
    try:
        source = Path(session.leadagent_repo_dir)
        source.mkdir(parents=True, exist_ok=True)
        with tarfile.open(source_archive) as archive:
            archive.extractall(source, filter="data")
        shutil.copyfile(source_archive, Path(session.leadagent_repro_dir) / "source.tar")
        session.commit_sha, session.image_id = task.commit_sha, task.image_id
        session.replay_source_archive_sha256 = task.source_archive_sha256
        session.build_system = session.selected_build_system = task.build_system
        try:
            runtime.create_container(session)
        finally:
            manager.save_session(session)
        session.status = "inspected"
        manager.save_session(session)
        plan = assemble_simple_plan(task, actions)
        workflow = SimpleBuildWorkflow(plan=plan, session=session, manager=manager, runtime=runtime, reference=reference, budget=PlanBudget(wall_clock_seconds=600, command_timeout_seconds=180))
        result["initial"] = workflow.run()
        if workflow.status == "needs_handoff" and repair_actions:
            save(root / "recovery-agent-packet.json", simple_agent_packet(task, current_plan=workflow.plan, handoff=workflow.handoff))
            revised = assemble_simple_plan(task, repair_actions, revision=2)
            workflow.apply_revision(handoff_id=workflow.handoff["handoff_id"], plan=revised, reason=repair_actions.reason)
            result["after_scripted_revision"] = workflow.run()
        if workflow.status == "primary_completed":
            result.update(workflow.postchecks(author_test_seconds=author_test_seconds))
        result.update(status=workflow.status, session_id=session.session_id, layers=workflow.layers, timings=workflow.timings)
    except Exception as exc:
        result.update(status="error", error_type=type(exc).__name__, error=str(exc))
        if workflow:
            result.update(layers=workflow.layers, timings=workflow.timings)
    finally:
        try:
            current = manager.load_session(session.session_id, session.thread_id)
            current, cleanup = operations.cleanup_and_finalize_compile_session_impl(session=current)
            result.update(cleanup=asdict(cleanup), session_status=current.status, container_id=current.container_id)
        except Exception as exc:
            result.update(cleanup=dict(succeeded=False), cleanup_error=f"{type(exc).__name__}: {exc}")
        if result.get("layers"):
            layers = result["layers"]
            layers["full_completed"] = full_completion(layers, result["cleanup"]["succeeded"])
        save(root / "result.json", result)
        operations._services = original
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--actions", type=Path, required=True)
    parser.add_argument("--repair-actions", type=Path)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--author-test-seconds", type=int, default=60)
    args = parser.parse_args()
    if args.author_test_seconds < 1:
        parser.error("作者测试时限必须为正数")
    result = run(
        task=PublicBuildTask.model_validate_json(args.task.read_text()),
        reference=BuildReference.model_validate_json(args.reference.read_text()),
        actions=ObservedBuildActions.model_validate_json(args.actions.read_text()),
        repair_actions=ObservedBuildActions.model_validate_json(args.repair_actions.read_text()) if args.repair_actions else None,
        source_archive=args.source_archive,
        output_root=args.output_root,
        author_test_seconds=args.author_test_seconds,
    )
    print(json.dumps({k: result.get(k) for k in ("status", "layers", "cleanup", "error")}, ensure_ascii=False))
    return 0 if result.get("layers", {}).get("primary_build_completed") and result["cleanup"]["succeeded"] and result.get("status") != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
